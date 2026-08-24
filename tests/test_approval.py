"""Focused tests for the lawyer approval workflow.

Runs against the seeded local PostgreSQL database. Drafts, approval decisions,
and audit events created by tests are removed again; a module-level guard
proves nothing leaks and the seeded dataset stays untouched.
"""

from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

# Make scripts/ importable so the independent source parser can be reused.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import func, select

from app.database.connection import SessionLocal, engine
from app.models import ApprovalDecision, AuditEvent, Draft, Request
from app.services.approval import (
    ApprovalWorkflowError,
    STATE_APPROVED,
    STATE_AWAITING_APPROVAL,
    STATE_REJECTED,
    approve_draft,
    reject_draft,
)
from app.services.drafting import create_draft

SEED_REQUEST_ID = "L-C-001"  # seeded request

APPROVER_REVIEWER = "L-02"  # can_approve = true
NO_AUTH_REVIEWER = "L-05"   # can_approve = false
ARABIC_DRAFT = "مسودة نهائية — C-09:\nالمدة سنة واحدة\n"


def _draft_count() -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(Draft)).scalar_one()


def _approval_count() -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count()).select_from(ApprovalDecision)
        ).scalar_one()


def _audit_count(*types: str) -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type.in_(types))
        ).scalar_one()


def _cleanup_draft_chain(request_id: str) -> None:
    with SessionLocal() as session:
        drafts = session.scalars(
            select(Draft).where(Draft.request_id == request_id)
        ).all()
        for d in drafts:
            for ad in session.scalars(
                select(ApprovalDecision).where(ApprovalDecision.draft_id == d.draft_id)
            ):
                session.delete(ad)
        for d in drafts:
            for evt in session.scalars(
                select(AuditEvent).where(AuditEvent.request_id == request_id)
            ):
                session.delete(evt)
            session.delete(d)
        session.commit()


@pytest.fixture(scope="module", autouse=True)
def guard_seed_and_counts():
    with SessionLocal() as session:
        assert session.get(Request, SEED_REQUEST_ID) is not None, "seed missing: request"
    base_d = _draft_count()
    base_a = _approval_count()
    base_app = _audit_count("approved")
    base_rej = _audit_count("rejected")
    yield
    assert _draft_count() == base_d, "test leaked Draft rows"
    assert _approval_count() == base_a, "test leaked ApprovalDecision rows"
    assert _audit_count("approved") == base_app, "test leaked approved events"
    assert _audit_count("rejected") == base_rej, "test leaked rejected events"


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


# ---------------------------------------------------------------------------
# Approval / rejection happy paths
# ---------------------------------------------------------------------------

def test_authorized_reviewer_approves_current_draft():
    with SessionLocal() as session:
        create_draft(session, request_id=SEED_REQUEST_ID, content="draft body v1")
        d2 = create_draft(session, request_id=SEED_REQUEST_ID, content="draft body v2")
        d2_id = d2.draft_id
        approval = approve_draft(
            session, draft_id=d2_id, reviewer_id=APPROVER_REVIEWER
        )
        approval_id = approval.approval_decision_id
        session.commit()

    try:
        with SessionLocal() as verify:
            assert verify.get(Draft, d2_id).approval_state == STATE_APPROVED
            row = verify.get(ApprovalDecision, approval_id)
            assert row.draft_id == d2_id
            assert row.reviewer_id == APPROVER_REVIEWER
            assert row.decision == "approved"
            assert row.draft_version == 2
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_authorized_reviewer_rejects_current_draft():
    with SessionLocal() as session:
        d1 = create_draft(session, request_id=SEED_REQUEST_ID, content="reject me v1")
        d1_id = d1.draft_id
        rejection = reject_draft(
            session, draft_id=d1_id, reviewer_id=APPROVER_REVIEWER
        )
        rejection_id = rejection.approval_decision_id
        session.commit()

    try:
        with SessionLocal() as verify:
            assert verify.get(Draft, d1_id).approval_state == STATE_REJECTED
            row = verify.get(ApprovalDecision, rejection_id)
            assert row.decision == "rejected"
            assert row.draft_version == 1
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_reviewer_without_approval_authority_rejected():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="auth check")
        d_id = d.draft_id
        session.commit()

    try:
        with SessionLocal() as session:
            with pytest.raises(ApprovalWorkflowError) as e:
                approve_draft(session, draft_id=d_id, reviewer_id=NO_AUTH_REVIEWER)
            assert "can_approve" in str(e.value) or "approval authority" in str(e.value)
            session.rollback()
        assert _approval_count() == 0
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_unknown_reviewer_rejected():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="auth check 2")
        d_id = d.draft_id
        session.commit()

    try:
        with SessionLocal() as session:
            with pytest.raises(ApprovalWorkflowError):
                approve_draft(session, draft_id=d_id, reviewer_id="L-9999")
            session.rollback()
        assert _approval_count() == 0
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_unknown_draft_rejected():
    with SessionLocal() as session:
        with pytest.raises(ApprovalWorkflowError):
            approve_draft(
                session, draft_id=uuid.uuid4(), reviewer_id=APPROVER_REVIEWER
            )
        session.rollback()


# ---------------------------------------------------------------------------
# Lifecycle / state rules
# ---------------------------------------------------------------------------

def test_stale_version_cannot_be_acted_upon():
    with SessionLocal() as session:
        d1 = create_draft(session, request_id=SEED_REQUEST_ID, content="v1 body")
        d2 = create_draft(session, request_id=SEED_REQUEST_ID, content="v2 body")
        d1_id, d2_id = d1.draft_id, d2.draft_id
        session.commit()

    try:
        with SessionLocal() as session:
            with pytest.raises(ApprovalWorkflowError):
                approve_draft(session, draft_id=d1_id, reviewer_id=APPROVER_REVIEWER)
            session.rollback()
        with SessionLocal() as session:
            approve_draft(session, draft_id=d2_id, reviewer_id=APPROVER_REVIEWER)
            session.commit()
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_invalid_transition_from_terminal_state_rejected():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="terminal check")
        d_id = d.draft_id
        approve_draft(session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER)
        session.commit()

    try:
        with SessionLocal() as session:
            with pytest.raises(ApprovalWorkflowError):
                reject_draft(session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER)
            session.rollback()
        assert _approval_count() == 1
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_v1_remains_immutable_after_v2_action():
    with SessionLocal() as session:
        d1 = create_draft(session, request_id=SEED_REQUEST_ID, content="v1 immutable body")
        d2 = create_draft(session, request_id=SEED_REQUEST_ID, content="v2 body")
        d1_id, d2_id = d1.draft_id, d2.draft_id
        session.commit()

    try:
        with SessionLocal() as session:
            reject_draft(session, draft_id=d2_id, reviewer_id=APPROVER_REVIEWER)
            session.commit()
        with SessionLocal() as verify:
            v1 = verify.get(Draft, d1_id)
            assert v1.content == "v1 immutable body"
            assert v1.approval_state == STATE_AWAITING_APPROVAL
            assert verify.scalars(
                select(ApprovalDecision).where(
                    ApprovalDecision.draft_id == d1_id
                )
            ).all() == []
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_arabic_draft_unchanged_through_approval():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content=ARABIC_DRAFT)
        d_id = d.draft_id
        approve_draft(session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER)
        session.commit()

    try:
        with SessionLocal() as verify:
            row = verify.get(Draft, d_id)
            assert row.content == ARABIC_DRAFT
            assert row.approval_state == STATE_APPROVED
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_approval_decision_fields_correct():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="field check")
        d_id = d.draft_id
        approval = approve_draft(
            session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER
        )
        approval_id = approval.approval_decision_id
        session.commit()

    try:
        with SessionLocal() as verify:
            row = verify.get(ApprovalDecision, approval_id)
            assert row.draft_id == d_id
            assert row.reviewer_id == APPROVER_REVIEWER
            assert row.decision == "approved"
            assert row.draft_version == 1
            assert row.decided_at is not None
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


# ---------------------------------------------------------------------------
# Audit behaviour (exact event types + metadata)
# ---------------------------------------------------------------------------

def test_approval_audit_event_exact_metadata():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="audit check")
        d_id = d.draft_id
        approval = approve_draft(
            session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER
        )
        approval_id = approval.approval_decision_id
        session.commit()

    try:
        with SessionLocal() as verify:
            events = verify.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"approval_decision:{approval_id}"
                )
            ).all()
            assert len(events) == 1
            evt = events[0]
            assert evt.event_type == "approved"
            assert evt.request_id == SEED_REQUEST_ID
            assert evt.actor_id == APPROVER_REVIEWER
            assert evt.detail_json == {
                "decision": "approved",
                "draft_version": 1,
                "reviewer_id": APPROVER_REVIEWER,
            }
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_rejection_audit_event_exact_metadata():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="reject audit")
        d_id = d.draft_id
        rejection = reject_draft(
            session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER
        )
        rejection_id = rejection.approval_decision_id
        session.commit()

    try:
        with SessionLocal() as verify:
            events = verify.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference
                    == f"approval_decision:{rejection_id}"
                )
            ).all()
            assert len(events) == 1
            assert events[0].event_type == "rejected"
            assert events[0].actor_id == APPROVER_REVIEWER
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


# ---------------------------------------------------------------------------
# Atomicity / failure / rollback
# ---------------------------------------------------------------------------

def test_failed_approval_leaves_nothing():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="failure check")
        d_id = d.draft_id
        session.commit()

    before_d = _draft_count()
    before_a = _approval_count()
    before_e = _audit_count("approved", "rejected")
    try:
        with SessionLocal() as session:
            with pytest.raises(ApprovalWorkflowError):
                approve_draft(session, draft_id=d_id, reviewer_id=NO_AUTH_REVIEWER)
            session.rollback()
        assert _draft_count() == before_d
        assert _approval_count() == before_a
        assert _audit_count("approved", "rejected") == before_e
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_failed_rejection_leaves_nothing():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="reject failure")
        d_id = d.draft_id
        session.commit()

    before_d = _draft_count()
    before_a = _approval_count()
    before_e = _audit_count("approved", "rejected")
    try:
        with SessionLocal() as session:
            with pytest.raises(ApprovalWorkflowError):
                reject_draft(session, draft_id=d_id, reviewer_id="L-9999")
            session.rollback()
        assert _draft_count() == before_d
        assert _approval_count() == before_a
        assert _audit_count("approved", "rejected") == before_e
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)


def test_rollback_removes_all_approval_writes():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="rollback check")
        d_id = d.draft_id
        approve_draft(session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER)
        session.rollback()

    assert _draft_count() == 0
    assert _approval_count() == 0
    assert _audit_count("approved", "rejected") == 0
    with SessionLocal() as verify:
        assert verify.get(Draft, d_id) is None


# ---------------------------------------------------------------------------
# Security boundary (no forbidden tables / raw_content; can_approve only)
# ---------------------------------------------------------------------------

def test_approval_queries_no_forbidden_tables_or_raw_content():
    with SessionLocal() as session:
        d = create_draft(session, request_id=SEED_REQUEST_ID, content="boundary check")
        d_id = d.draft_id
        session.commit()

    try:
        with sql_spy() as statements:
            with SessionLocal() as session:
                approve_draft(session, draft_id=d_id, reviewer_id=APPROVER_REVIEWER)
                session.rollback()

        forbidden = (
            "matter_assignment",
            "access_decision",
            "contract",
            "data_room_file",
            "review_standard_clause",
            "finding",
            "citation",
            "obligation",
            "escalation",
            "request.content",
            "raw_content",
            " request ",
        )
        touched = [s for s in statements if any(t in s for t in forbidden)]
        assert not touched, f"approval queried forbidden tables/content: {touched}"
        # Permitted: draft lookups, team_member can_approve, approval_decision,
        # audit_event.
        permitted = ("team_member", "approval_decision", "audit_event", " from draft ")
        assert any(p in s for s in statements for p in permitted)
    finally:
        _cleanup_draft_chain(SEED_REQUEST_ID)