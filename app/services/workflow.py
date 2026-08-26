"""Thin application orchestrator.

Coordinated call sequence only — no business/security logic lives here. Every
stage delegates to the existing deterministic services in the order dictated
by docs/system-architecture.md §4 (Request Lifecycle) and the PRD:

    Request Intake      -> app.services.request_intake.submit_request
    Classification      -> app.services.request_intake.classify_request
    Access Control      -> app.services.access_control.record_access_decision
    Document Retrieval  -> app.services.document_retrieval (authorized only)
    Rulebook Review     -> app.services.rulebook_review.review_contract
    Obligation Sweep    -> app.services.obligation_sweep.sweep_obligations
    Drafting            -> app.services.drafting.create_draft
    Lawyer Approval     -> app.services.approval.approve_draft / reject_draft

Findings and Citations are produced inside rulebook_review, which persists
through app.services.review (create_grounded_finding / create_ungrounded_finding)
with already-retrieved clause ORM instances.

Transaction ownership: this module NEVER commits. All stages run inside the
caller's transaction. A failure raised by any lower-level service propagates
unchanged (no blanket catching), leaving the session ready for the caller's
rollback — partial state cannot persist.

Documented workflow decisions (ambiguity resolutions):
- Access decision is recorded BEFORE any retrieval. An unauthorized recorded
  AccessDecision stops the workflow: :class:`WorkflowAccessDenied` is raised,
  the decision row stays in the session (SEC-006 logging), and retrieval is
  never reached.
- Retrieval only happens via :mod:`app.services.document_retrieval`, which
  itself enforces the recorded-authorization gate. The orchestrator never
  queries contract / data_room / review_standard tables directly.
- No new audit event types are invented; each service writes its own
  documented events (intake, classified, document_retrieved, finding_produced,
  escalated, draft_created/draft_edited, approved/rejected).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Organisation, AuditEvent, Request
from app.services import (  # noqa: E402  (import order kept flat for clarity)
    access_control,
    analysis_run,
    approval,
    document_retrieval,
    drafting,
    llm,
    obligation_sweep,
    request_intake,
    rulebook_review,
)

# ---------------------------------------------------------------------------
# Workflow exceptions
# ---------------------------------------------------------------------------

class WorkflowError(Exception):
    """Base class for orchestration-level failures."""


class WorkflowStageError(WorkflowError):
    """A composed workflow stage failed; the underlying error propagates.

    ``stage`` names the documented pipeline step that failed.
    """

    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


class WorkflowAccessDenied(WorkflowError):
    """Raised when the recorded AccessDecision outcome is 'unauthorized'.

    The unauthorized AccessDecision row is already added to the session by
    access_control (SEC-006 logging); the caller decides whether to commit
    (keep the log) or roll back.
    """


# ---------------------------------------------------------------------------
# Stage names (for WorkflowStageError reporting only)
# ---------------------------------------------------------------------------

STAGE_INTAKE = "intake"
STAGE_CLASSIFY = "classification"
STAGE_ACCESS = "access_control"
STAGE_RETRIEVE = "document_retrieval"
STAGE_REVIEW = "rulebook_review"
STAGE_SWEEP = "obligation_sweep"
STAGE_DRAFT = "drafting"
STAGE_APPROVAL = "approval"


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewWorkflowResult:
    """Outcome of the composed intake -> access -> retrieval -> review flow."""

    access_decision: object
    contracts: tuple = ()
    clauses: tuple = ()
    standard_clauses: tuple = ()
    findings: tuple = ()
    sweep_result: object | None = None
    analysis_run: object | None = None


# ---------------------------------------------------------------------------
# Intake + classification
# ---------------------------------------------------------------------------

def intake_and_classify(
    session: Session,
    *,
    request_id: str,
    requester_id: str,
    raw_content: str,
    org_id: str | None,
    request_type: str,
    created_at=None,
):
    """Run the documented Intake -> Classification sequence for one request.

    Calls :func:`request_intake.submit_request` then
    :func:`request_intake.classify_request`. Returns the classified Request.
    """
    try:
        request = request_intake.submit_request(
            session,
            request_id=request_id,
            requester_id=requester_id,
            raw_content=raw_content,
            org_id=org_id,
            created_at=created_at,
        )
    except Exception as exc:  # propagate with stage context, no swallowing
        raise WorkflowStageError(STAGE_INTAKE, str(exc)) from exc

    try:
        classified = request_intake.classify_request(
            session,
            request_id=request_id,
            request_type=request_type,
        )
    except Exception as exc:
        raise WorkflowStageError(STAGE_CLASSIFY, str(exc)) from exc
    return classified


def auto_intake_and_classify(
    session: Session,
    *,
    request_id: str,
    requester_id: str,
    raw_content: str,
    org_id: str | None,
    created_at=None,
):
    """Run Intake -> AI Classification for a request missing explicit types.
    
    If the LLM needs clarification or cannot confidently identify the org (when 
    not explicitly provided), the request is left in 'insufficient' status.
    """
    try:
        request = request_intake.submit_request(
            session,
            request_id=request_id,
            requester_id=requester_id,
            raw_content=raw_content,
            org_id=org_id,
            created_at=created_at,
        )
    except Exception as exc:
        raise WorkflowStageError(STAGE_INTAKE, str(exc)) from exc

    # Fetch available orgs to pass to the LLM
    try:
        orgs = session.query(Organisation).filter(Organisation.status == "active").all()
        available_orgs = {org.org_id: org.name for org in orgs}
        
        result = llm.classify_request_via_llm(raw_content, available_orgs)
        
        final_org_id = org_id if org_id is not None else result.org_id
        
        if result.needs_clarification or (not final_org_id and not result.org_id):
            # Cannot confidently classify or map org
            request.status = "insufficient"
            session.add(
                AuditEvent(
                    request_id=request_id,
                    event_type="classification_failed",
                    actor_id=None,
                    detail_reference=f"request:{request_id}",
                    detail_json={"reason": result.reason, "needs_clarification": result.needs_clarification},
                )
            )
            return request

        # Valid classification
        if org_id is None and final_org_id:
            request.org_id = final_org_id
            
        classified = request_intake.classify_request(
            session,
            request_id=request_id,
            request_type=result.request_type,
        )
        return classified
    except Exception as exc:
        raise WorkflowStageError(STAGE_CLASSIFY, str(exc)) from exc


def resolve_insufficient_request(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
    request_type: str,
):
    """Manually resolve a request left in 'insufficient' state by AI classification.
    
    Checks that the user has access to the org_id they are trying to assign.
    """
    # 1. Authorize the user against the org they want to assign
    access_result = access_control.check_access(session, member_id, org_id)
    if not access_result.authorized:
        raise WorkflowAccessDenied(access_result.basis)
        
    try:
        # Check org exists and is active (handled mostly by check_access, but we ensure status here)
        org = session.get(Organisation, org_id)
        if not org or org.status != "active":
            raise request_intake.RequestIntakeError(f"Organisation {org_id} is inactive or does not exist.")
            
        request = session.get(Request, request_id)
        if not request:
            raise request_intake.RequestIntakeError(f"unknown request_id {request_id}")
            
        if request.status not in ("intake", "insufficient"):
            raise request_intake.RequestIntakeError(f"Request cannot be resolved from status: {request.status}")

        # Update org
        request.org_id = org_id
        
        # We classify it and move status to classified
        classified = request_intake.classify_request(
            session,
            request_id=request_id,
            request_type=request_type,
        )
        
        # Add a specific audit event for manual resolution
        session.add(
            AuditEvent(
                request_id=request_id,
                event_type="manual_classification",
                actor_id=member_id,
                detail_reference=f"request:{request_id}",
                detail_json={"org_id": org_id, "request_type": request_type},
            )
        )
        return classified
    except Exception as exc:
        raise WorkflowStageError(STAGE_CLASSIFY, str(exc)) from exc


# ---------------------------------------------------------------------------
# Access + retrieval + review (+ optional obligation sweep)
# ---------------------------------------------------------------------------

def run_review(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
    contract_id: str | None = None,
    reference_date: date | None = None,
    suppressed_obligation_ids: frozenset | set = frozenset(),
) -> ReviewWorkflowResult:
    """Compose Access Control -> Retrieval -> Rulebook Review -> (Sweep).

    - Records the AccessDecision FIRST (access_control). If the outcome is
      'unauthorized', raises :class:`WorkflowAccessDenied` and stops before
      any document is retrieved.
    - Retrieves the organisation's contracts (and a specific contract's
      clauses when ``contract_id`` is supplied) plus the review-standard
      corpus, all through :mod:`app.services.document_retrieval`.
    - Runs :func:`rulebook_review.review_contract` with ONLY the retrieved
      clause ORM instances — never bare identifiers, never an independent
      lookup.
    - When ``reference_date`` is provided, runs the obligation sweep for the
      organisation (documented as following review).
    """
    # Validate the request exists BEFORE recording the access decision so an
    # unknown id maps cleanly to 404 and no orphan rows can be created.
    if session.get(Request, request_id) is None:
        exc = request_intake.RequestIntakeError(
            f"unknown request_id {request_id!r}"
        )
        raise WorkflowStageError(STAGE_RETRIEVE, str(exc)) from exc

    try:
        decision = access_control.record_access_decision(
            session,
            request_id=request_id,
            member_id=member_id,
            org_id=org_id,
        )
        session.flush()
    except Exception as exc:
        raise WorkflowStageError(STAGE_ACCESS, str(exc)) from exc

    if decision.outcome != "authorized":
        raise WorkflowAccessDenied(
            f"AccessDecision for request {request_id!r} (member {member_id!r}, "
            f"org {org_id!r}) is {decision.outcome!r}; workflow stopped"
        )

    # Phase 1: one AnalysisRun per review execution. Findings created below
    # belong to this run; the deterministic summary is snapshotted at the end.
    run = analysis_run.start_run(session, request_id=request_id)

    try:
        contracts = tuple(
            document_retrieval.retrieve_contracts(
                session,
                request_id=request_id,
                member_id=member_id,
                org_id=org_id,
            )
        )
    except Exception as exc:
        analysis_run.fail_run(session, run=run, reason=str(exc))
        raise WorkflowStageError(STAGE_RETRIEVE, str(exc)) from exc

    try:
        standard_clauses = tuple(
            document_retrieval.retrieve_review_standard_clauses(
                session,
                request_id=request_id,
                member_id=member_id,
                org_id=org_id,
            )
        )
    except Exception as exc:
        analysis_run.fail_run(session, run=run, reason=str(exc))
        raise WorkflowStageError(STAGE_RETRIEVE, str(exc)) from exc

    clauses: list = []
    try:
        if contract_id is not None:
            clauses = list(
                document_retrieval.retrieve_contract_clauses(
                    session,
                    request_id=request_id,
                    member_id=member_id,
                    org_id=org_id,
                    contract_id=contract_id,
                )
            )
        else:
            for contract in contracts:
                clauses.extend(
                    document_retrieval.retrieve_contract_clauses(
                        session,
                        request_id=request_id,
                        member_id=member_id,
                        org_id=org_id,
                        contract_id=contract.contract_id,
                    )
                )
    except Exception as exc:
        raise WorkflowStageError(STAGE_RETRIEVE, str(exc)) from exc

    try:
        findings, engine = rulebook_review.review_contract(
            session,
            request_id=request_id,
            contract_clauses=clauses,
            standard_clauses=list(standard_clauses),
            analysis_run_id=run.analysis_run_id,
        )
    except Exception as exc:
        analysis_run.fail_run(session, run=run, reason=str(exc))
        raise WorkflowStageError(STAGE_REVIEW, str(exc)) from exc

    # Deterministic result snapshot: mark the run completed with a factual
    # summary of its own findings before any downstream stage can fail.
    analysis_run.complete_run(
        session, run=run, findings=tuple(findings), engine=engine
    )

    sweep_result = None
    if reference_date is not None:
        try:
            sweep_result = obligation_sweep.sweep_obligations(
                session,
                reference_date=reference_date,
                org_id=org_id,
                suppressed_obligation_ids=suppressed_obligation_ids,
                standard_clauses=list(standard_clauses),
            )
        except Exception as exc:
            raise WorkflowStageError(STAGE_SWEEP, str(exc)) from exc

    return ReviewWorkflowResult(
        access_decision=decision,
        contracts=contracts,
        clauses=tuple(clauses),
        standard_clauses=standard_clauses,
        findings=tuple(findings),
        sweep_result=sweep_result,
        analysis_run=run,
    )


def run_obligation_sweep(
    session: Session,
    *,
    reference_date: date,
    org_id: str | None = None,
    owner_id: str | None = None,
    suppressed_obligation_ids: frozenset | set = frozenset(),
    standard_clauses=None,
):
    """Dedicated wrapper: delegate to :func:`obligation_sweep.sweep_obligations`."""
    try:
        return obligation_sweep.sweep_obligations(
            session,
            reference_date=reference_date,
            org_id=org_id,
            owner_id=owner_id,
            suppressed_obligation_ids=suppressed_obligation_ids,
            standard_clauses=standard_clauses,
        )
    except Exception as exc:
        raise WorkflowStageError(STAGE_SWEEP, str(exc)) from exc


# ---------------------------------------------------------------------------
# Drafting + approval
# ---------------------------------------------------------------------------

def prepare_draft(
    session: Session,
    *,
    request_id: str,
    content: str,
    created_at=None,
    created_by: str | None = None,
):
    """Delegate to :func:`drafting.create_draft` (thin wrapper)."""
    try:
        return drafting.create_draft(
            session,
            request_id=request_id,
            content=content,
            created_at=created_at,
            created_by=created_by,
        )
    except Exception as exc:
        raise WorkflowStageError(STAGE_DRAFT, str(exc)) from exc


def approve_current_draft(
    session: Session,
    *,
    draft_id,
    reviewer_id: str,
):
    """Delegate to :func:`approval.approve_draft` (thin wrapper)."""
    try:
        return approval.approve_draft(
            session,
            draft_id=draft_id,
            reviewer_id=reviewer_id,
        )
    except Exception as exc:
        raise WorkflowStageError(STAGE_APPROVAL, str(exc)) from exc


def reject_current_draft(
    session: Session,
    *,
    draft_id,
    reviewer_id: str,
):
    """Delegate to :func:`approval.reject_draft` (thin wrapper)."""
    try:
        return approval.reject_draft(
            session,
            draft_id=draft_id,
            reviewer_id=reviewer_id,
        )
    except Exception as exc:
        raise WorkflowStageError(STAGE_APPROVAL, str(exc)) from exc