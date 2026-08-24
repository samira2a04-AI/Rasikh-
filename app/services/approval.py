"""Lawyer approval workflow (FR-029–FR-032, APR-001–APR-005, Rule 5;
docs/data-schema.md §8, docs/system-architecture.md §9).

Deterministic persistence gate for recording lawyer decisions on drafts:

- **Authority (APR-004 / schema §8).** The reviewer must be an existing
  TeamMember with ``can_approve = true``. The schema notes this is "enforced
  in app" — implemented here. No other authorization policy is invented: the
  specification ties approval authority to the ``can_approve`` capability,
  not to matter assignment.
- **Currency.** Only the CURRENT version of a request's draft chain may be
  acted upon; acting on a superseded (stale) version is rejected. This
  implements the Approval Gate precondition that a satisfying decision must
  be "against the current version" (docs/data-schema.md §8, FR-032).
- **Transitions.** ``approve`` and ``reject`` are valid from the open states
  (``awaiting_approval``, and ``edited`` for spec-compliance with the edit
  flow described in §8/architecture §9). ``approved`` and ``rejected`` are
  terminal: a decided draft cannot be decided again, and one draft row
  carries exactly one ApprovalDecision (history continues via NEW versions,
  which the drafting service appends immutably).
- **Records.** Each decision inserts one ``approval_decision`` row with
  draft_id, reviewer_id, decision, draft_version (the exact version decided
  upon — APR-004) and updates ONLY the current draft's ``approval_state``.
  Previous versions are never modified.
- **Audit.** Exactly one append-only AuditEvent per decision using the
  specified event types ``approved`` / ``rejected`` (docs/data-schema.md §5),
  actor = reviewer (APR-004: who made the decision), detail_reference pointing
  at the decision row, detail_json carrying decision/version metadata.

Security boundary: touches only ``draft``, ``team_member`` (identifier +
can_approve), ``approval_decision``, and ``audit_event``. Request content is
never read; contracts/clauses/data-room files/findings/citations/obligations/
escalations are never queried; no AI/network/fuzzy matching. The caller owns
the transaction — decision + state change + audit event roll back together.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApprovalDecision, AuditEvent, Draft, TeamMember

EVENT_APPROVED = "approved"
EVENT_REJECTED = "rejected"

STATE_AWAITING_APPROVAL = "awaiting_approval"
STATE_EDITED = "edited"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"

# States from which a lawyer decision may be taken (open states). approved /
# rejected are terminal per docs/data-schema.md §8.
_OPEN_STATES = frozenset({STATE_AWAITING_APPROVAL, STATE_EDITED})


class ApprovalWorkflowError(ValueError):
    """Raised when an approval/rejection cannot be performed as requested."""


def _load_current_draft(session: Session, draft_id: object) -> Draft:
    """Load the draft and verify it is the current version of its request."""
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ApprovalWorkflowError(f"unknown draft_id {draft_id!r}")

    max_version = session.execute(
        select(func.max(Draft.version)).where(Draft.request_id == draft.request_id)
    ).scalar_one()
    if draft.version != max_version:
        raise ApprovalWorkflowError(
            f"draft {draft_id!r} is version {draft.version}, but the current "
            f"version for request {draft.request_id!r} is {max_version}; "
            "stale versions cannot be approved or rejected"
        )
    return draft


def _validate_reviewer(session: Session, reviewer_id: str) -> TeamMember:
    reviewer = session.execute(
        select(TeamMember.member_id, TeamMember.can_approve).where(
            TeamMember.member_id == reviewer_id
        )
    ).first()
    if reviewer is None:
        raise ApprovalWorkflowError(f"unknown reviewer_id {reviewer_id!r}")
    if not reviewer.can_approve:
        raise ApprovalWorkflowError(
            f"reviewer {reviewer_id!r} does not have approval authority "
            "(can_approve=false)"
        )
    # Re-fetch the ORM instance for relationship-free use below.
    member = session.get(TeamMember, reviewer_id)
    assert member is not None
    return member


def _decide(
    session: Session,
    *,
    draft_id: object,
    reviewer_id: str,
    decision: str,
) -> ApprovalDecision:
    """Shared deterministic path for approve/reject (caller owns transaction)."""
    event_type = EVENT_APPROVED if decision == "approved" else EVENT_REJECTED
    target_state = STATE_APPROVED if decision == "approved" else STATE_REJECTED

    draft = _load_current_draft(session, draft_id)
    _validate_reviewer(session, reviewer_id)

    if draft.approval_state not in _OPEN_STATES:
        raise ApprovalWorkflowError(
            f"draft {draft_id!r} is {draft.approval_state!r}; a decision has "
            "already been recorded and the state is terminal"
        )

    existing = (
        session.execute(
            select(ApprovalDecision.approval_decision_id)
            .where(ApprovalDecision.draft_id == draft.draft_id)
            .limit(1)
        ).first()
        is not None
    )
    if existing:
        raise ApprovalWorkflowError(
            f"draft {draft_id!r} already carries an ApprovalDecision; further "
            "changes continue through new draft versions"
        )

    approval = ApprovalDecision(
        draft_id=draft.draft_id,
        reviewer_id=reviewer_id,
        decision=decision,
        draft_version=draft.version,
    )
    session.add(approval)
    session.flush()  # assign PK for the audit reference

    draft.approval_state = target_state

    session.add(
        AuditEvent(
            request_id=draft.request_id,
            event_type=event_type,
            actor_id=reviewer_id,  # APR-004: record who decided
            detail_reference=f"approval_decision:{approval.approval_decision_id}",
            detail_json={
                "decision": decision,
                "draft_version": draft.version,
                "reviewer_id": reviewer_id,
            },
        )
    )
    session.flush()  # atomic: decision + state + audit surface violations now
    return approval


def approve_draft(
    session: Session,
    *,
    draft_id: object,
    reviewer_id: str,
) -> ApprovalDecision:
    """Record a lawyer's APPROVAL of the current draft version (FR-029).

    Creates the ApprovalDecision, moves the draft to ``approved``, and writes
    the ``approved`` audit event — atomically within the caller's transaction.
    """
    return _decide(session, draft_id=draft_id, reviewer_id=reviewer_id, decision="approved")


def reject_draft(
    session: Session,
    *,
    draft_id: object,
    reviewer_id: str,
) -> ApprovalDecision:
    """Record a lawyer's REJECTION of the current draft version (FR-031).

    Creates the ApprovalDecision, moves the draft to ``rejected`` (terminal,
    non-final), and writes the ``rejected`` audit event — atomically within
    the caller's transaction.
    """
    return _decide(session, draft_id=draft_id, reviewer_id=reviewer_id, decision="rejected")