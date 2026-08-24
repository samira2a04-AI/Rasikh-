"""Obligation threshold sweep + escalation routing (FR-016–FR-018, OBL-*,
ESC-004; rulebook sections 5.2 and 6).

Deterministic workflow over the stored obligation calendar:

- **Bands (rulebook 6.2).** The stored ``obligation.band`` column — populated
  from clause 6.2 thresholds against the dataset reference date — is the
  authoritative classification. This sweep NEVER mutates it. When the caller
  supplies the section 6.2 standard clauses, each obligation's band is also
  recomputed from ``due_date`` + the explicit ``reference_date`` purely as a
  drift report; mismatches are surfaced, never corrected here.
- **Escalation (rulebook 6.2 + 5.2).** An OVERDUE obligation "escalates to
  the responsible lawyer at once" (6.2); section 5.2 likewise requires
  escalation for "a deadline that is already missed". The responsible lawyer
  is the obligation's owner (``routed_to_id = owner_id``) — confirmed by the
  ALERTS ground truth (OB-04 -> its owner L-07). Reason uses the schema's
  ``missed_deadline`` value. Target semantics follow the schema CHECK: exactly
  one of ``obligation_id`` / ``request_id``; obligation-based escalations set
  ``obligation_id`` and leave ``request_id`` NULL.
- **Urgent / reminder / on_track.** These produce named alerts in the sweep
  result only. No rulebook clause turns them into Escalation rows, so none
  are created.
- **Historical/closed suppression.** The ALERTS ground-truth note records
  OB-01 as historical/closed ("not re-alerted as a live obligation"). The
  mechanism is a generic explicit ``suppressed_obligation_ids`` parameter:
  the runtime service never hard-codes dataset-specific rows; callers pass
  the set derived from the authoritative ALERTS entry. Suppressed
  obligations are reported under ``suppressed`` and never escalated.

Idempotency: an overdue obligation receives at most one open
``missed_deadline`` escalation. Existing Escalation rows with the same
 ``(obligation_id, reason='missed_deadline')`` suppress duplicates
deterministically at service level — no new database constraint.

Audit: one append-only ``escalated`` AuditEvent per escalation CREATED (a
type named by docs/data-schema.md §5; actor NULL — system action;
``detail_reference`` points at the escalation row). Urgent/reminder/
on_track/suppressed outcomes write nothing — no event types are invented.

Security: reads ``obligation`` rows only (plus the caller-supplied rulebook
clauses). No MatterAssignment, AccessDecision, request-content, contract, or
data-room access; no LLM; no fuzzy matching. The caller owns the transaction
— nothing is committed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Escalation, Obligation, ReviewStandardClause

EVENT_ESCALATED = "escalated"
REASON_MISSED_DEADLINE = "missed_deadline"

# ---------------------------------------------------------------------------
# Band computation from rulebook 6.2 thresholds (never hard-coded)
# ---------------------------------------------------------------------------

@dataclass
class BandThresholds:
    """Thresholds parsed from supplied rulebook clause 6.2 text."""

    on_track_gt: int | None = None   # "more than N days"
    reminder_lo: int | None = None   # "N to M days"
    reminder_hi: int | None = None
    urgent_le: int | None = None     # "N days or fewer"

    @property
    def complete(self) -> bool:
        return (
            self.on_track_gt is not None
            and self.reminder_lo is not None
            and self.reminder_hi is not None
            and self.urgent_le is not None
        )


def derive_band_thresholds(standard_clauses: list[ReviewStandardClause]) -> BandThresholds:
    """Parse the alert thresholds out of supplied rulebook clause 6.2."""
    thresholds = BandThresholds()
    clause_62 = next(
        (c for c in standard_clauses if c.clause_number == "6.2"), None
    )
    if clause_62 is None:
        return thresholds
    body = clause_62.text
    m = re.search(r"more than (\d+) days", body, flags=re.IGNORECASE)
    if m:
        thresholds.on_track_gt = int(m.group(1))
    m = re.search(r"(\d+) to (\d+) days", body, flags=re.IGNORECASE)
    if m:
        thresholds.reminder_lo, thresholds.reminder_hi = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+) days or fewer", body, flags=re.IGNORECASE)
    if m:
        thresholds.urgent_le = int(m.group(1))
    return thresholds


def compute_band(due_date: date, reference_date: date, t: BandThresholds) -> str | None:
    """Classify a due date against the reference date using parsed thresholds.

    Returns None when the supplied rulebook text did not yield a complete
    threshold set (nothing is guessed).
    """
    urgent_le = t.urgent_le
    reminder_lo = t.reminder_lo
    reminder_hi = t.reminder_hi
    on_track_gt = t.on_track_gt
    if None in (urgent_le, reminder_lo, reminder_hi, on_track_gt):
        return None
    assert urgent_le is not None and reminder_lo is not None  # narrowed below
    assert reminder_hi is not None and on_track_gt is not None

    if due_date < reference_date:
        return "overdue"
    days_until = (due_date - reference_date).days
    if days_until <= urgent_le:
        return "urgent"
    if reminder_lo <= days_until <= reminder_hi:
        return "reminder"
    if days_until > on_track_gt:
        return "on_track"
    return None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObligationSnapshot:
    obligation_id: str
    org_id: str
    owner_id: str
    due_date: date
    stored_band: str
    computed_band: str | None


@dataclass(frozen=True)
class EscalationCreated:
    escalation_id: object
    obligation_id: str
    reason: str
    routed_to_id: str


@dataclass(frozen=True)
class ObligationSweepResult:
    reference_date: date
    inspected: tuple[ObligationSnapshot, ...] = field(default_factory=tuple)
    on_track: tuple[str, ...] = ()
    reminder: tuple[str, ...] = ()
    urgent: tuple[str, ...] = ()
    overdue: tuple[str, ...] = ()
    suppressed: tuple[str, ...] = ()
    escalations_created: tuple[EscalationCreated, ...] = ()
    already_escalated: tuple[str, ...] = ()  # duplicates skipped (idempotency)
    band_drift: tuple[tuple[str, str, str], ...] = ()  # (id, stored, computed)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sweep_obligations(
    session: Session,
    *,
    reference_date: date,
    org_id: str | None = None,
    owner_id: str | None = None,
    suppressed_obligation_ids: frozenset[str] | set[str] = frozenset(),
    standard_clauses: list[ReviewStandardClause] | None = None,
) -> ObligationSweepResult:
    """Run the Section 5–6 obligation sweep and create required escalations.

    - Buckets every inspected obligation by its STORED band.
    - Creates one ``missed_deadline`` Escalation per unsuppressed overdue
      obligation, routed to the obligation's owner, unless an equivalent
      escalation already exists (idempotent).
    - Appends one ``escalated`` AuditEvent per escalation created.
    - Never mutates stored bands; never commits (caller owns transaction).
    """
    stmt = select(Obligation).order_by(Obligation.obligation_id)
    if org_id is not None:
        stmt = stmt.where(Obligation.org_id == org_id)
    if owner_id is not None:
        stmt = stmt.where(Obligation.owner_id == owner_id)
    obligations = list(session.scalars(stmt).all())

    thresholds = (
        derive_band_thresholds(standard_clauses) if standard_clauses is not None else BandThresholds()
    )

    snapshots: list[ObligationSnapshot] = []
    buckets: dict[str, list[str]] = {
        "on_track": [],
        "reminder": [],
        "urgent": [],
        "overdue": [],
    }
    suppressed: list[str] = []
    drift: list[tuple[str, str, str]] = []

    for o in obligations:
        computed = (
            compute_band(o.due_date, reference_date, thresholds)
            if thresholds.complete
            else None
        )
        if computed is not None and computed != o.band:
            drift.append((o.obligation_id, o.band, computed))
        snapshots.append(
            ObligationSnapshot(
                obligation_id=o.obligation_id,
                org_id=o.org_id,
                owner_id=o.owner_id,
                due_date=o.due_date,
                stored_band=o.band,
                computed_band=computed,
            )
        )
        if o.obligation_id in suppressed_obligation_ids:
            suppressed.append(o.obligation_id)
        elif o.band in buckets:
            buckets[o.band].append(o.obligation_id)

    # Escalate unsuppressed overdue obligations to their responsible lawyer.
    escalations_created: list[EscalationCreated] = []
    already_escalated: list[str] = []
    for obligation_id in buckets["overdue"]:
        obligation = next(o for o in obligations if o.obligation_id == obligation_id)
        existing = (
            session.execute(
                select(Escalation.escalation_id)
                .where(
                    Escalation.obligation_id == obligation_id,
                    Escalation.reason == REASON_MISSED_DEADLINE,
                )
                .limit(1)
            ).first()
            is not None
        )
        if existing:
            already_escalated.append(obligation_id)
            continue

        escalation = Escalation(
            obligation_id=obligation_id,
            request_id=None,  # obligation-targeted: exactly-one CHECK satisfied
            reason=REASON_MISSED_DEADLINE,
            routed_to_id=obligation.owner_id,  # rulebook 6.2 "responsible lawyer"
        )
        session.add(escalation)
        session.flush()  # assign PK for the audit reference

        session.add(
            AuditEvent(
                request_id=None,
                event_type=EVENT_ESCALATED,
                actor_id=None,  # system action
                detail_reference=f"escalation:{escalation.escalation_id}",
                detail_json={
                    "obligation_id": obligation_id,
                    "reason": REASON_MISSED_DEADLINE,
                    "routed_to_id": obligation.owner_id,
                },
            )
        )
        escalations_created.append(
            EscalationCreated(
                escalation_id=escalation.escalation_id,
                obligation_id=obligation_id,
                reason=REASON_MISSED_DEADLINE,
                routed_to_id=obligation.owner_id,
            )
        )

    return ObligationSweepResult(
        reference_date=reference_date,
        inspected=tuple(snapshots),
        on_track=tuple(buckets["on_track"]),
        reminder=tuple(buckets["reminder"]),
        urgent=tuple(buckets["urgent"]),
        overdue=tuple(buckets["overdue"]),
        suppressed=tuple(suppressed),
        escalations_created=tuple(escalations_created),
        already_escalated=tuple(already_escalated),
        band_drift=tuple(drift),
    )