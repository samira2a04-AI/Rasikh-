"""Focused tests for the obligation threshold sweep + escalation routing.

Runs against the seeded obligation calendar (reference date 2026-07-01, the
dataset's stated "today"). Escalations and audit events created by tests are
removed again; a module-level guard proves nothing leaks and that stored
bands are never mutated.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

# Make scripts/ importable so the independent source parser can be reused.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import load_data  # noqa: E402  — scripts/load_data.py

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import func, select

from app.database.connection import SessionLocal, engine
from app.models import AuditEvent, Escalation, Obligation, ReviewStandardClause
from app.services.obligation_sweep import (
    BandThresholds,
    compute_band,
    derive_band_thresholds,
    sweep_obligations,
)

REFERENCE_DATE = date(2026, 7, 1)  # dataset "today" per data/README.md


def _std_62() -> list[ReviewStandardClause]:
    with SessionLocal() as session:
        clause = session.scalars(
            select(ReviewStandardClause).where(
                ReviewStandardClause.clause_number == "6.2"
            )
        ).one()
        session.expunge(clause)
        return [clause]


def _stored_bands() -> dict[str, str]:
    with SessionLocal() as session:
        rows = session.scalars(select(Obligation)).all()
        return {o.obligation_id: o.band for o in rows}


def _escalation_count() -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(Escalation)).scalar_one()


def _escalated_event_count() -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "escalated")
        ).scalar_one()


def _cleanup_escalations(escalation_ids) -> None:
    with SessionLocal() as session:
        for eid in escalation_ids:
            row = session.get(Escalation, eid)
            if row is not None:
                session.delete(row)
            for evt in session.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"escalation:{eid}"
                )
            ):
                session.delete(evt)
        session.commit()


@pytest.fixture(scope="module", autouse=True)
def guard_seed_and_counts():
    """Fail fast if seed data is missing; prove no rows leak from tests."""
    bands = _stored_bands()
    assert set(bands) == {
        "OB-01", "OB-02", "OB-03", "OB-04", "OB-05", "OB-06", "OB-07", "OB-08"
    }, "seed missing: obligations"

    baseline_esc = _escalation_count()
    baseline_evt = _escalated_event_count()
    yield
    assert _escalation_count() == baseline_esc, "test leaked Escalation rows"
    assert _escalated_event_count() == baseline_evt, "test leaked escalated events"
    assert _stored_bands() == bands, "stored obligation bands were mutated"


@contextmanager
def sql_spy():
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    sa_event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        sa_event.remove(engine, "before_cursor_execute", record)


SUPPRESSED = frozenset({"OB-01"})  # ALERTS: historical/closed — not re-alerted


# ---------------------------------------------------------------------------
# Bucketing against the answer_key ALERTS ground truth
# ---------------------------------------------------------------------------

def test_full_sweep_matches_alerts_ground_truth():
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            suppressed_obligation_ids=SUPPRESSED,
            standard_clauses=_std_62(),
        )
        session.rollback()

    assert result.reference_date == REFERENCE_DATE
    assert sorted(result.overdue) == ["OB-04"]          # OB-04 overdue handling
    assert sorted(result.urgent) == ["OB-02"]           # OB-02 urgent handling
    assert sorted(result.reminder) == ["OB-03", "OB-05"]  # both reminders preserved
    assert sorted(result.on_track) == ["OB-06", "OB-07", "OB-08"]
    assert result.suppressed == ("OB-01",)              # OB-01 historical/closed
    assert len(result.inspected) == 8


def test_suppressed_obligation_is_never_escalated():
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            suppressed_obligation_ids=SUPPRESSED,
        )
        session.rollback()

    # Without suppression OB-01 would be overdue; with it, only OB-04 escalates.
    assert result.escalations_created and all(
        e.obligation_id == "OB-04" for e in result.escalations_created
    )
    assert "OB-01" not in result.overdue
    assert result.suppressed == ("OB-01",)


def test_unsuppressed_overdue_would_escalate_mechanically():
    # Demonstrates the mechanism generically: without the ALERTS-derived
    # suppression set, every mechanically-overdue obligation escalates.
    with SessionLocal() as session:
        result = sweep_obligations(session, reference_date=REFERENCE_DATE)
        ids = [e.escalation_id for e in result.escalations_created]
        targets = sorted(e.obligation_id for e in result.escalations_created)
        session.rollback()
    assert targets == ["OB-01", "OB-04"]  # both are mechanically overdue
    _cleanup_escalations(ids)


# ---------------------------------------------------------------------------
# Escalation record semantics
# ---------------------------------------------------------------------------

def test_escalation_record_semantics_and_persistence():
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            suppressed_obligation_ids=SUPPRESSED,
        )
        session.commit()
        created_ids = [e.escalation_id for e in result.escalations_created]
        assert len(created_ids) == 1

    try:
        with SessionLocal() as verify:
            row = verify.get(Escalation, created_ids[0])
            assert row is not None
            assert row.reason == "missed_deadline"       # correct schema reason
            assert row.obligation_id == "OB-04"          # obligation-targeted...
            assert row.request_id is None                # ...request_id NULL (CHECK)
            assert row.routed_to_id == "L-07"            # valid member = owner (ALERTS)
            assert row.created_at is not None
    finally:
        _cleanup_escalations(created_ids)


def test_routed_to_is_the_responsible_lawyer_owner():
    # Rulebook 6.2: overdue "escalates to the responsible lawyer at once";
    # ALERTS confirms OB-04 -> L-07, which is exactly OB-04's seeded owner.
    with SessionLocal() as session:
        owner = session.get(Obligation, "OB-04").owner_id
    assert owner == "L-07"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_sweep_is_idempotent_no_duplicate_escalations():
    all_ids: list[list] = []
    try:
        with SessionLocal() as session:
            first = sweep_obligations(
                session,
                reference_date=REFERENCE_DATE,
                suppressed_obligation_ids=SUPPRESSED,
            )
            session.commit()
            all_ids.append([e.escalation_id for e in first.escalations_created])
        count_after_first = _escalation_count()

        with SessionLocal() as session:
            second = sweep_obligations(
                session,
                reference_date=REFERENCE_DATE,
                suppressed_obligation_ids=SUPPRESSED,
            )
            session.rollback()  # second run created nothing to persist

        assert len(first.escalations_created) == 1
        assert second.escalations_created == ()
        assert second.already_escalated == ("OB-04",)
        assert _escalation_count() == count_after_first == 1
    finally:
        for ids in all_ids:
            _cleanup_escalations(ids)


def test_pre_existing_escalation_suppresses_duplicate():
    # Simulate an escalation that already exists (as if a prior run committed).
    with SessionLocal() as session:
        pre = Escalation(
            obligation_id="OB-04",
            request_id=None,
            reason="missed_deadline",
            routed_to_id="L-07",
        )
        session.add(pre)
        session.commit()
        pre_id = pre.escalation_id

    try:
        with SessionLocal() as session:
            result = sweep_obligations(
                session,
                reference_date=REFERENCE_DATE,
                suppressed_obligation_ids=SUPPRESSED,
            )
            session.rollback()
        assert result.escalations_created == ()
        assert result.already_escalated == ("OB-04",)
        assert _escalation_count() == 1
    finally:
        _cleanup_escalations([pre_id])


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def test_filter_by_org_id():
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            org_id="ORG-1033",
            suppressed_obligation_ids=SUPPRESSED,
        )
        session.rollback()
    assert [s.obligation_id for s in result.inspected] == ["OB-04"]
    assert result.urgent == () and result.reminder == ()


def test_filter_by_owner_id():
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            owner_id="L-01",
        )
        session.rollback()
    assert [s.obligation_id for s in result.inspected] == ["OB-02"]


# ---------------------------------------------------------------------------
# Determinism / reference date / band immutability
# ---------------------------------------------------------------------------

def test_deterministic_output_across_runs():
    runs = []
    for _ in range(2):
        with SessionLocal() as session:
            result = sweep_obligations(
                session,
                reference_date=REFERENCE_DATE,
                suppressed_obligation_ids=SUPPRESSED,
                standard_clauses=_std_62(),
            )
            session.rollback()
            runs.append(
                (
                    tuple(sorted(result.on_track)),
                    tuple(sorted(result.reminder)),
                    tuple(sorted(result.urgent)),
                    tuple(sorted(result.overdue)),
                    tuple(sorted(result.suppressed)),
                    tuple(sorted(e.obligation_id for e in result.escalations_created)),
                )
            )
    assert runs[0] == runs[1]


def test_reference_date_is_explicit_not_system_clock():
    # A different explicit reference date changes the computed drift view but
    # never touches stored data; the result echoes exactly what was passed.
    other_date = date(2026, 8, 1)
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=other_date,
            standard_clauses=_std_62(),
        )
        session.rollback()
    assert result.reference_date == other_date
    bands_before = _stored_bands()
    assert _stored_bands() == bands_before  # unchanged by the sweep


def test_stored_band_never_mutated_even_with_drift():
    # Recompute against a LATER reference date: computed bands differ from
    # stored ones, the drift is reported, and stored values stay intact.
    before = _stored_bands()
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=date(2026, 9, 1),
            standard_clauses=_std_62(),
        )
        session.rollback()
    assert result.band_drift, "expected drift to be reported for the later date"
    assert _stored_bands() == before


def test_band_thresholds_derived_from_rulebook_not_hard_coded():
    thresholds = derive_band_thresholds(_std_62())
    assert isinstance(thresholds, BandThresholds)
    assert thresholds.on_track_gt == 30      # parsed from clause 6.2 text
    assert (thresholds.reminder_lo, thresholds.reminder_hi) == (8, 30)
    assert thresholds.urgent_le == 7

    # Boundary behaviour of the parsed thresholds @ 2026-07-01:
    # strictly past due -> overdue; due today = 0 days away -> urgent.
    assert compute_band(date(2026, 6, 30), REFERENCE_DATE, thresholds) == "overdue"
    assert compute_band(date(2026, 7, 1), REFERENCE_DATE, thresholds) == "urgent"
    assert compute_band(date(2026, 7, 8), REFERENCE_DATE, thresholds) == "urgent"
    assert compute_band(date(2026, 7, 9), REFERENCE_DATE, thresholds) == "reminder"
    assert compute_band(date(2026, 7, 31), REFERENCE_DATE, thresholds) == "reminder"
    assert compute_band(date(2026, 8, 1), REFERENCE_DATE, thresholds) == "on_track"


def test_incomplete_rulebook_yields_no_computed_band():
    empty = BandThresholds()
    assert compute_band(date(2026, 7, 5), REFERENCE_DATE, empty) is None


# ---------------------------------------------------------------------------
# Security boundary
# ---------------------------------------------------------------------------

def test_sweep_queries_no_authorization_or_document_tables():
    std62 = _std_62()  # fetched OUTSIDE the spy by the test
    try:
        with sql_spy() as statements:
            with SessionLocal() as session:
                result = sweep_obligations(
                    session,
                    reference_date=REFERENCE_DATE,
                    suppressed_obligation_ids=SUPPRESSED,
                    standard_clauses=std62,
                )
                session.rollback()

        forbidden = (
            "matter_assignment",
            "access_decision",
            "contract",
            "data_room_file",
            "review_standard_clause",
            "from request",
            "raw_content",
        )
        touched = [s for s in statements if any(t in s for t in forbidden)]
        assert not touched, f"sweep queried forbidden tables/content: {touched}"
        assert any("from obligation" in s for s in statements), "sweep should read obligations"
    finally:
        _cleanup_escalations([e.escalation_id for e in result.escalations_created])


# ---------------------------------------------------------------------------
# Transaction ownership & atomicity
# ---------------------------------------------------------------------------

def test_rollback_leaves_no_partial_escalations():
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            suppressed_obligation_ids=SUPPRESSED,
        )
        assert len(result.escalations_created) == 1
        session.rollback()  # caller chose to abort

    assert _escalation_count() == 0
    assert _escalated_event_count() == 0


# ---------------------------------------------------------------------------
# Audit behaviour
# ---------------------------------------------------------------------------

def test_escalated_audit_event_written_once_per_escalation():
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            suppressed_obligation_ids=SUPPRESSED,
        )
        session.commit()
        created = result.escalations_created[0]

    try:
        with SessionLocal() as verify:
            events = verify.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"escalation:{created.escalation_id}"
                )
            ).all()
            assert len(events) == 1
            evt = events[0]
            assert evt.event_type == "escalated"     # specified event type
            assert evt.request_id is None            # obligation-based
            assert evt.actor_id is None              # system action
            assert evt.detail_json == {
                "obligation_id": "OB-04",
                "reason": "missed_deadline",
                "routed_to_id": "L-07",
            }
            assert evt.occurred_at is not None
    finally:
        _cleanup_escalations([created.escalation_id])


def test_no_audit_events_for_non_escalation_outcomes():
    baseline = _escalated_event_count()
    with SessionLocal() as session:
        result = sweep_obligations(
            session,
            reference_date=REFERENCE_DATE,
            org_id="ORG-1019",  # OB-02 urgent only — no escalation path
            suppressed_obligation_ids=SUPPRESSED,
        )
        session.rollback()
    assert result.urgent == ("OB-02",)
    assert result.escalations_created == ()
    assert _escalated_event_count() == baseline