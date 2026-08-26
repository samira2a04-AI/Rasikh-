"""AI draft generation (FR-007/PRD \"drafts grounded responses\"; AI-002).

This service lets a lawyer generate a draft from the ALREADY-COMPLETED request
analysis and the HUMAN-REVIEWED findings of a request, then persists that
draft through the normal append-only draft boundary
(:func:`app.services.drafting.create_draft`) so the new version begins in
``awaiting_approval`` and is approved or rejected exactly like every other
draft (APR-001–APR-003, Rule 5). It deliberately does NOT touch the approval
workflow, does NOT approve anything, and does NOT bypass human review.

Preconditions (each enforced deterministically — no inventing of policies):
- The request exists.
- The request has a COMPLETED AnalysisRun (the "already-completed request
  analysis"). A missing/failed/pending analysis cannot be drafted from.
- Every finding of the request is human-reviewed (``status == 'reviewed'``).
  Findings entered as ``open`` must be reviewed first: generating a draft from
  unreviewed findings would short-circuit the human safeguard, which is
  explicitly out of scope to bypass.

Inputs it reads: ``request`` (identifier + type + raw_content so the memo can
answer what was asked), the completed AnalysisRun summary, and the request's
findings together with the clause text each finding CITES. It never queries
contract/data-room tables on its own and never accepts bare clause ids — all
source text comes from citations that the review layer already grounded.

Engine fallback: the LLM draft helper returns ``None`` when no API key is
configured (or raises on network/API failure); this service then uses the
deterministic composer (:func:`_compose_deterministic_draft`) so generation
never hard-fails in local/testing environments. No draft is empty: content is
validated by :func:`drafting.create_draft`.

Transaction convention: no ``commit()`` here. All reads/writes happen inside
the caller's transaction and the final ``drafting.create_draft`` records the
``draft_created``/``draft_edited`` audit event, so a failure rolls back with
no partial rows.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, Draft, Finding, Request
from app.services import drafting, llm
from app.services.analysis_run import latest_completed_run

logger = logging.getLogger(__name__)

# REVIEWED_FINDING_STATUS is the terminal human-review state written by
# app.services.review.review_finding.
REVIEWED_FINDING_STATUS = "reviewed"

_REQUEST_TYPE_LABELS = {
    "contract_review": "Contract Review",
    "consultation": "Consultation",
    "meeting_prep": "Meeting Preparation",
    "obligation_check": "Obligation Check",
}


class AIDraftingError(Exception):
    """Raised when a draft cannot be generated as requested."""


def _require_request(session: Session, request_id: str) -> Request:
    request = session.get(Request, request_id)
    if request is None:
        raise AIDraftingError(f"unknown request_id {request_id!r}")
    return request


def _require_completed_analysis(session: Session, request_id: str) -> AnalysisRun:
    run = latest_completed_run(session, request_id=request_id)
    if run is None:
        raise AIDraftingError(
            f"request {request_id!r} has no completed analysis; run the analysis "
            "and complete human review of its findings before generating a draft"
        )
    return run


def _citation_source_lines(finding: Finding) -> list[str]:
    """Human-readable clause references for a finding, only from recorded citations."""
    lines: list[str] = []
    for citation in finding.citations:
        if citation.contract_clause is not None:
            label = (
                citation.contract_clause.clause_label
                or citation.contract_clause.contract_id
            )
            lines.append(f"    - Contract clause {label}: {citation.contract_clause.text}")
        elif citation.standard_clause is not None:
            lines.append(
                f"    - Rulebook clause {citation.standard_clause.clause_number}: "
                f"{citation.standard_clause.text}"
            )
    if not lines and not finding.grounded:
        lines.append("    - (finding states this is not addressed in the documents)")
    return lines


def _build_context(
    session: Session,
    *,
    request_id: str,
    request: Request,
    run: AnalysisRun,
    findings: list[Finding],
) -> str:
    """Deterministic, structured context for both the LLM and the fallback."""
    parts: list[str] = []
    type_label = _REQUEST_TYPE_LABELS.get(request.request_type or "", "Legal")
    parts.append(f"REQUEST ID: {request_id}")
    parts.append(f"REQUEST TYPE: {type_label}")
    parts.append(f"REQUEST ASKED: {request.raw_content.strip()}")
    parts.append("")
    parts.append("COMPLETED ANALYSIS SUMMARY:")
    parts.append(f"  {run.summary if run.summary else '(no summary recorded)'}")
    parts.append("")
    parts.append("HUMAN-REVIEWED FINDINGS:")
    if not findings:
        parts.append("  (no findings)")
    for i, finding in enumerate(findings, start=1):
        parts.append(f"{i}. {finding.statement}")
        if finding.checklist_area:
            parts.append(f"   Checklist area: {finding.checklist_area}")
        if finding.risk_rating:
            parts.append(f"   Risk: {finding.risk_rating}")
        if finding.sharia_sensitive_flag:
            parts.append("   Sharia-sensitive flag: YES")
        parts.append(f"   Grounded: {finding.grounded}")
        parts.extend(_citation_source_lines(finding))
    return "\n".join(parts)


def _compose_deterministic_draft(
    *,
    request_id: str,
    request: Request,
    run: AnalysisRun,
    findings: list[Finding],
    context: str,
) -> str:
    """Deterministic fallback composing a cited memo from the supplied data."""
    type_label = _REQUEST_TYPE_LABELS.get(request.request_type or "", "Legal")
    lines: list[str] = []
    lines.append(f"Draft — {type_label} — {request_id}")
    lines.append("This AI-generated draft was composed from the completed "
                 "analysis and the human-reviewed findings.")
    lines.append("")
    lines.append("Overview")
    lines.append(f"{run.summary if run.summary else 'The analysis produced no summary.'}")
    lines.append("")
    lines.append("Reviewed findings")
    if not findings:
        lines.append("- None recorded.")
    for i, finding in enumerate(findings, start=1):
        lines.append(f"{i}. {finding.statement}")
        if finding.risk_rating:
            lines.append(f"   Risk: {finding.risk_rating}")
        for citation_line in _citation_source_lines(finding):
            lines.append(citation_line)
        if finding.checklist_area:
            lines.append(f"   Checklist area: {finding.checklist_area}")
    lines.append("")
    lines.append(
        "This document is an AI-generated draft. It is subject to lawyer review "
        "and approval and is not final until approved."
    )
    content = "\n".join(lines).strip()
    if not content:
        # Belts-and-braces: create_draft rejects empty content anyway.
        return context.strip()
    return content


def generate_ai_draft(
    session: Session,
    *,
    request_id: str,
    created_by: str | None = None,
) -> Draft:
    """Generate and persist the next draft version for a request.

    Reads the request's completed analysis and human-reviewed findings, composes
    a grounded memo (LLM when available, deterministic fallback otherwise), and
    persists it via :func:`drafting.create_draft` — append-only, in
    ``awaiting_approval``, with the invoking lawyer recorded as author so the
    existing separation-of-duties gate still applies.
    """
    request = _require_request(session, request_id)
    run = _require_completed_analysis(session, request_id)
    findings = _require_reviewed_findings(session, request_id)

    context = _build_context(
        session,
        request_id=request_id,
        request=request,
        run=run,
        findings=findings,
    )

    content = None
    try:
        content = llm.synthesize_draft_via_llm(context)
    except Exception as exc:
        # LLM unavailable (quota/network/API): compose deterministically instead
        # of failing the request. The output remains grounded in the supplied
        # findings.
        logger.warning("LLM draft synthesis failed; using deterministic draft: %s", exc)
        content = None

    if content is None:
        content = _compose_deterministic_draft(
            request_id=request_id,
            request=request,
            run=run,
            findings=findings,
            context=context,
        )

    return drafting.create_draft(
        session,
        request_id=request_id,
        content=content,
        created_by=created_by,
    )


def _require_reviewed_findings(session: Session, request_id: str) -> list[Finding]:
    """Return the request's findings, refusing to draft from any open one."""
    findings = list(
        session.scalars(
            select(Finding).where(Finding.request_id == request_id)
        ).all()
    )
    if not findings:
        raise AIDraftingError(
            f"request {request_id!r} has no findings to draft from; run the "
            "analysis first"
        )
    open_findings = [f for f in findings if f.status != REVIEWED_FINDING_STATUS]
    if open_findings:
        raise AIDraftingError(
            f"all findings must be human-reviewed before generating a draft: "
            f"{len(open_findings)} of {len(findings)} finding(s) still open for "
            f"review"
        )
    return findings