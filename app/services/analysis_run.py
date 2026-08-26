"""AnalysisRun lifecycle service (Phase 1: real AI result persistence).

Owns the small explicit lifecycle of one analysis execution:

    running -> completed | failed

and writes the documented audit events:

    ai_analysis_started / ai_analysis_completed / ai_analysis_failed

The result summary is a DETERMINISTIC synthesis of the run's own persisted
findings (counts, highest severity, groundedness, sharia flags). No narrative
is invented. The caller owns the transaction — no commit here.

Engine metadata records which evaluator produced the findings ('llm' or
'deterministic_fallback') so fallback output is distinguishable from Gemini
output and never presented as if it came from the model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from app.models import AnalysisRun, AuditEvent, Finding

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

EVENT_STARTED = "ai_analysis_started"
EVENT_COMPLETED = "ai_analysis_completed"
EVENT_FAILED = "ai_analysis_failed"

ENGINE_LLM = "llm"
ENGINE_FALLBACK = "deterministic_fallback"

# Severity levels recognised when summarising verbatim risk ratings
# (ratings are free text such as 'Low risk'; matching is by substring).
_SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def _severity_level(risk_rating: str | None) -> str | None:
    if not risk_rating:
        return None
    r = risk_rating.lower()
    for level in reversed(_SEVERITY_ORDER):
        if level in r:
            return level
    return None


def start_run(session: Session, *, request_id: str) -> AnalysisRun:
    """Create a run in 'running' status with its ai_analysis_started event."""
    run = AnalysisRun(request_id=request_id, status=STATUS_RUNNING)
    session.add(run)
    session.flush()  # assign PK for the audit reference

    session.add(
        AuditEvent(
            request_id=request_id,
            event_type=EVENT_STARTED,
            actor_id=None,  # system action
            detail_reference=f"analysis_run:{run.analysis_run_id}",
            detail_json={"analysis_run_id": str(run.analysis_run_id)},
        )
    )
    session.flush()
    return run

def build_summary(findings: Sequence[Finding]) -> tuple[str, dict]:
    """Deterministically synthesise the factual result of a set of findings.

    Returns (summary_text, counts_dict). Every sentence states something the
    findings themselves record — no conclusions, scores or recommendations.
    """
    total = len(findings)
    grounded = sum(1 for f in findings if f.grounded)
    ungrounded = total - grounded
    levels = [(_severity_level(f.risk_rating) or "unrated") for f in findings]
    high = sum(1 for lv in levels if lv in ("high", "critical"))
    sharia = sum(1 for f in findings if f.sharia_sensitive_flag)

    order = {lv: i for i, lv in enumerate(_SEVERITY_ORDER)}
    rated = [lv for lv in levels if lv != "unrated"]
    highest = max(rated, key=lambda lv: order[lv]) if rated else None

    parts = [
        f"Automated review produced {total} finding{'s' if total != 1 else ''}.",
        f"{grounded} grounded in cited contract/standard clauses; "
        f"{ungrounded} explicitly not addressed in the documents.",
    ]
    if highest:
        parts.append(f"Highest recorded severity: {highest}.")
        parts.append(f"{high} high-severity finding{'s' if high != 1 else ''}.")
    else:
        parts.append("No severity ratings were recorded on these findings.")
    if sharia:
        parts.append(
            f"{sharia} finding{'s are' if sharia != 1 else ' is'} flagged "
            "Sharia-sensitive."
        )

    counts = {
        "finding_count": total,
        "high_severity_count": high,
        "grounded_count": grounded,
        "ungrounded_count": ungrounded,
    }
    return " ".join(parts), counts


def complete_run(
    session: Session,
    *,
    run: AnalysisRun,
    findings: Sequence[Finding],
    engine: str,
) -> AnalysisRun:
    """Snapshot the run's counts, store the deterministic summary, audit it."""
    summary, counts = build_summary(findings)
    now = datetime.now(timezone.utc)

    run.status = STATUS_COMPLETED
    run.engine = engine
    run.summary = summary
    run.completed_at = now
    run.finding_count = counts["finding_count"]
    run.high_severity_count = counts["high_severity_count"]
    run.grounded_count = counts["grounded_count"]
    run.ungrounded_count = counts["ungrounded_count"]

    # Associate any findings missing a run reference (defensive).
    for finding in findings:
        if finding.analysis_run_id is None:
            finding.analysis_run_id = run.analysis_run_id

    session.add(
        AuditEvent(
            request_id=run.request_id,
            event_type=EVENT_COMPLETED,
            actor_id=None,
            detail_reference=f"analysis_run:{run.analysis_run_id}",
            detail_json={
                "analysis_run_id": str(run.analysis_run_id),
                "finding_count": counts["finding_count"],
                "engine": engine,
            },
        )
    )
    session.flush()
    return run

def fail_run(session: Session, *, run: AnalysisRun, reason: str) -> AnalysisRun:
    """Mark a run failed with its reason and write the failure audit event."""
    run.status = STATUS_FAILED
    run.failure_reason = reason[:500]
    run.completed_at = datetime.now(timezone.utc)

    session.add(
        AuditEvent(
            request_id=run.request_id,
            event_type=EVENT_FAILED,
            actor_id=None,
            detail_reference=f"analysis_run:{run.analysis_run_id}",
            detail_json={
                "analysis_run_id": str(run.analysis_run_id),
                "reason": run.failure_reason,
            },
        )
    )
    session.flush()
    return run


def latest_completed_run(session: Session, *, request_id: str) -> AnalysisRun | None:
    """The most recent completed run for a request (the current analysis)."""
    return (
        session.query(AnalysisRun)
        .filter(
            AnalysisRun.request_id == request_id,
            AnalysisRun.status == STATUS_COMPLETED,
        )
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.analysis_run_id.desc())
        .first()
    )
