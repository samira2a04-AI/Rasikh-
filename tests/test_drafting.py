"""Focused tests for the draft persistence boundary.

Runs against the seeded local PostgreSQL database. Drafts and audit events
created by tests are removed again; a module-level guard proves nothing
leaks and the seeded dataset stays untouched.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# Make scripts/ importable so the independent source parser can be reused.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import func, select

from app.database.connection import SessionLocal, engine
from app.models import AuditEvent, Draft, Request
from app.services.drafting import (
    EVENT_DRAFT_CREATED,
    EVENT_DRAFT_EDITED,
    DraftingError,
    create_draft,
)

# Built without escape sequences so the Arabic text survives file transport
# byte-for-byte; joined with newline characters at runtime.
_NL = chr(10)
ARABIC_CONTENT = _NL.join(
    [
        "مسودة المراجعة — اتفاقية التوريد C-09:",
        "المدة سنة واحدة مع تجديد تلقائي ما لم يُخطر الطرف الآخر قبل ستين (60) يوماً.",
        "غرامة التأخير 5,000 ريال تحتاج مراجعة العلامة.   ",
    ]
)


def _draft_count() -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(Draft)).scalar_one()


def _draft_created_events() -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "draft_created")
        ).scalar_one()


def _draft_edited_events() -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "draft_edited")
        ).scalar_one()


def _cleanup_drafts(draft_ids) -> None:
    with SessionLocal() as session:
        for did in draft_ids:
            row = session.get(Draft, did)
            if row is not None:
                session.delete(row)
            for evt in session.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"draft:{did}"
                )
            ):
                session.delete(evt)
        session.commit()


@pytest.fixture(scope="module", autouse=True)
def guard_seed_and_counts():
    """Fail fast if seed data is missing; prove no rows leak from tests."""
    with SessionLocal() as session:
        assert session.get(Request, "L-C-001") is not None, "seed missing: request L-C-001"
    baseline_drafts = _draft_count()
    baseline_created = _draft_created_events()
    baseline_edited = _draft_edited_events()
    yield
    assert _draft_count() == baseline_drafts, "test leaked Draft rows"
    assert _draft_created_events() == baseline_created, "test leaked draft_created events"
    assert _draft_edited_events() == baseline_edited, "test leaked draft_edited events"


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
# Versioning
# ---------------------------------------------------------------------------

def test_first_second_third_draft_versions_sequence():
    ids: list = []
    versions: list[int] = []
    try:
        with SessionLocal() as session:
            d1 = create_draft(session, request_id="L-C-001", content="Draft v1 body.")
            d2 = create_draft(session, request_id="L-C-001", content="Draft v2 body.")
            d3 = create_draft(session, request_id="L-C-001", content="Draft v3 body.")
            versions = [d1.version, d2.version, d3.version]
            ids = [d1.draft_id, d2.draft_id, d3.draft_id]
            session.commit()

        assert versions == [1, 2, 3]                       # deterministic ordering

        with SessionLocal() as verify:
            rows = verify.scalars(
                select(Draft).where(Draft.request_id == "L-C-001").order_by(Draft.version)
            ).all()
            assert [r.version for r in rows] == [1, 2, 3]
            assert [r.content for r in rows] == [
                "Draft v1 body.",
                "Draft v2 body.",
                "Draft v3 body.",
            ]
            # every version starts awaiting_approval; prior drafts immutable
            assert all(r.approval_state == "awaiting_approval" for r in rows)
    finally:
        _cleanup_drafts(ids)


def test_versions_are_request_scoped():
    ids: list = []
    try:
        with SessionLocal() as session:
            a1 = create_draft(session, request_id="L-C-001", content="Request A v1.")
            b1 = create_draft(session, request_id="L-C-002", content="Request B v1.")
            a2 = create_draft(session, request_id="L-C-001", content="Request A v2.")
            session.commit()
            ids = [a1.draft_id, b1.draft_id, a2.draft_id]
            va = (a1.version, a2.version)
            vb = b1.version
        assert va == (1, 2) and vb == 1
    finally:
        _cleanup_drafts(ids)


def test_duplicate_content_creates_new_version_never_overwrites():
    ids: list = []
    try:
        with SessionLocal() as session:
            d1 = create_draft(session, request_id="L-C-004", content="Identical text.")
            first_id, first_version, first_content = (
                d1.draft_id,
                d1.version,
                d1.content,
            )
            ids.append(first_id)
            d2 = create_draft(session, request_id="L-C-004", content="Identical text.")
            second_id, second_version = d2.draft_id, d2.version
            ids.append(second_id)
            session.commit()

        assert first_id != second_id
        assert (first_version, second_version) == (1, 2)

        with SessionLocal() as verify:
            original = verify.get(Draft, first_id)
            assert original.version == first_version          # unchanged
            assert original.content == first_content          # byte-identical
            assert verify.get(Draft, second_id) is not None   # new row appended
    finally:
        _cleanup_drafts(ids)


# ---------------------------------------------------------------------------
# Content handling
# ---------------------------------------------------------------------------

def test_arabic_content_preserved_byte_for_byte():
    ids: list = []
    try:
        with SessionLocal() as session:
            draft = create_draft(session, request_id="L-C-009", content=ARABIC_CONTENT)
            session.commit()
            ids = [draft.draft_id]
        with SessionLocal() as verify:
            row = verify.get(Draft, ids[0])
            assert row.content == ARABIC_CONTENT              # exact, incl. trailing spaces
    finally:
        _cleanup_drafts(ids)


def test_empty_and_whitespace_content_rejected():
    before = _draft_count()
    whitespace_only = " ".join([" ", "", ""]) + chr(9) + _NL  # spaces + tab + newline
    with SessionLocal() as session:
        with pytest.raises(DraftingError):
            create_draft(session, request_id="L-C-001", content="")
        with pytest.raises(DraftingError):
            create_draft(session, request_id="L-C-001", content=whitespace_only)
        session.rollback()
    assert _draft_count() == before


def test_non_string_content_rejected():
    before = _draft_count()
    with SessionLocal() as session:
        with pytest.raises(DraftingError):
            create_draft(session, request_id="L-C-001", content=None)  # type: ignore[arg-type]
        session.rollback()
    assert _draft_count() == before


def test_unknown_request_rejected():
    before = _draft_count()
    with SessionLocal() as session:
        with pytest.raises(DraftingError):
            create_draft(
                session, request_id="TST-NO-SUCH-REQUEST", content="body"
            )
        session.rollback()
    assert _draft_count() == before


def test_explicit_created_at_honoured():
    ids: list = []
    created_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    try:
        with SessionLocal() as session:
            draft = create_draft(
                session, request_id="L-C-001", content="body", created_at=created_at
            )
            session.commit()
            ids = [draft.draft_id]
        with SessionLocal() as verify:
            row = verify.get(Draft, ids[0])
            assert row.created_at == created_at
            assert row.updated_at == created_at
    finally:
        _cleanup_drafts(ids)


# ---------------------------------------------------------------------------
# Audit behaviour
# ---------------------------------------------------------------------------

def test_audit_event_created_once_per_draft_with_correct_type():
    ids: list = []
    try:
        with SessionLocal() as session:
            d1 = create_draft(session, request_id="L-C-001", content="v1")
            d2 = create_draft(session, request_id="L-C-001", content="v2")
            session.commit()
            ids = [d1.draft_id, d2.draft_id]

        with SessionLocal() as verify:
            e1 = verify.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"draft:{ids[0]}"
                )
            ).one()
            e2 = verify.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"draft:{ids[1]}"
                )
            ).one()
            assert e1.event_type == EVENT_DRAFT_CREATED       # version 1
            assert e2.event_type == EVENT_DRAFT_EDITED        # later version
            assert e1.request_id == "L-C-001" and e2.request_id == "L-C-001"
            assert e1.actor_id is None and e2.actor_id is None
            assert e1.detail_json == {"version": 1}
            assert e2.detail_json == {"version": 2}           # no content leakage
            assert e1.occurred_at is not None and e2.occurred_at is not None
    finally:
        _cleanup_drafts(ids)


def test_failed_creation_leaves_no_draft_and_no_audit_event():
    before_d = _draft_count()
    before_c = _draft_created_events()
    before_e = _draft_edited_events()
    with SessionLocal() as session:
        with pytest.raises(DraftingError):
            create_draft(session, request_id="TST-NO-SUCH-REQUEST", content="x")
        session.rollback()
    assert _draft_count() == before_d
    assert _draft_created_events() == before_c
    assert _draft_edited_events() == before_e


def test_rollback_removes_draft_and_audit_event():
    before_d = _draft_count()
    with SessionLocal() as session:
        draft = create_draft(session, request_id="L-C-001", content="to be rolled back")
        assert draft.version >= 1
        session.rollback()  # caller aborts

    assert _draft_count() == before_d
    with SessionLocal() as verify:
        events = verify.scalars(
            select(AuditEvent).where(
                AuditEvent.detail_reference == f"draft:{draft.draft_id}"
            )
        ).all()
        assert events == []                                   # no orphan audit event


# ---------------------------------------------------------------------------
# Security boundary
# ---------------------------------------------------------------------------

def test_drafting_queries_no_forbidden_tables():
    try:
        with sql_spy() as statements:
            with SessionLocal() as session:
                draft = create_draft(
                    session, request_id="L-C-001", content="boundary check"
                )
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
            "approval_decision",
            "team_member",
            "organisation",
            "raw_content",
        )
        touched = [s for s in statements if any(t in s for t in forbidden)]
        assert not touched, f"drafting queried forbidden tables: {touched}"
        allowed_request_read = any("select request.request_id" in s for s in statements)
        allowed_draft_insert = any("insert into draft" in s for s in statements)
        assert allowed_request_read and allowed_draft_insert
    finally:
        pass