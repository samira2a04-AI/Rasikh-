"""Focused tests for the request intake + classification service.

Runs against the seeded local PostgreSQL database. Tests create temporary
Request rows (with their audit events) and remove them again; a module-level
guard proves the seeded dataset and audit log are left untouched.
"""

from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
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
from app.models import AuditEvent, Organisation, Request, TeamMember
from app.services.request_intake import (
    CLASSIFIABLE_REQUEST_TYPES,
    RequestIntakeError,
    classify_request,
    submit_request,
)

RAW_CONTENT_SAMPLE = (
    "Please review the Sadara supply agreement (C-01) — term, liability, and payment.\n"
    "سطر تجريبي بالعربية\n"
    "  indented line with trailing spaces   \n"
)


def _cleanup_request(request_id: str) -> None:
    """Remove a temporary request and its audit events."""
    with SessionLocal() as session:
        for evt in session.scalars(
            select(AuditEvent).where(AuditEvent.request_id == request_id)
        ):
            session.delete(evt)
        row = session.get(Request, request_id)
        if row is not None:
            session.delete(row)
        session.commit()


def _request_count() -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(Request)).scalar_one()


def _audit_count(*event_types: str) -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type.in_(event_types))
        ).scalar_one()


@pytest.fixture(scope="module", autouse=True)
def guard_seed_and_counts():
    """Fail fast if seed data is missing; prove no rows leak from tests."""
    with SessionLocal() as session:
        assert session.get(TeamMember, "L-02") is not None, "seed missing: L-02"
        assert session.get(Organisation, "ORG-1007") is not None, "seed missing: ORG-1007"
    baseline_requests = _request_count()
    baseline_intake = _audit_count("intake")
    baseline_classified = _audit_count("classified")
    yield
    assert _request_count() == baseline_requests, "test leaked Request rows"
    assert _audit_count("intake") == baseline_intake, "test leaked intake events"
    assert _audit_count("classified") == baseline_classified, "test leaked classified events"


@contextmanager
def sql_spy():
    """Capture every SQL statement executed inside the block."""
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    sa_event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        sa_event.remove(engine, "before_cursor_execute", record)


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

def test_valid_request_creation_persists_all_fields():
    created_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    with SessionLocal() as session:
        request = submit_request(
            session,
            request_id="TST-INTAKE-001",
            requester_id="L-02",
            raw_content=RAW_CONTENT_SAMPLE,
            org_id="ORG-1007",
            created_at=created_at,
        )
        session.commit()
        request_id = request.request_id

    try:
        with SessionLocal() as verify:
            row = verify.get(Request, request_id)
            assert row is not None
            # 2. correct requester persistence
            assert row.requester_id == "L-02"
            # 3. correct organisation persistence
            assert row.org_id == "ORG-1007"
            # 5. raw_content preserved exactly
            assert row.raw_content == RAW_CONTENT_SAMPLE
            # 6. initial status is 'intake'; type still unassigned
            assert row.status == "intake"
            assert row.request_type is None
            assert row.created_at == created_at
    finally:
        _cleanup_request(request_id)


def test_created_at_defaults_to_server_now():
    with SessionLocal() as session:
        request = submit_request(
            session,
            request_id="TST-INTAKE-002",
            requester_id="L-04",
            raw_content="plain body",
        )
        session.commit()
        request_id = request.request_id
    try:
        with SessionLocal() as verify:
            row = verify.get(Request, request_id)
            assert row.created_at is not None  # server-side now() applied
            assert row.org_id is None  # matter may be unknown at intake
    finally:
        _cleanup_request(request_id)


def test_raw_content_preserved_exactly_including_arabic_and_whitespace():
    with SessionLocal() as session:
        request = submit_request(
            session,
            request_id="TST-INTAKE-003",
            requester_id="L-05",
            raw_content=RAW_CONTENT_SAMPLE,
        )
        session.commit()
        request_id = request.request_id
    try:
        with SessionLocal() as verify:
            row = verify.get(Request, request_id)
            stored = row.raw_content
        assert stored == RAW_CONTENT_SAMPLE  # byte-for-byte, no stripping
        assert ARABIC_RE.search(stored)
    finally:
        _cleanup_request(request_id)


def test_invalid_requester_rejected():
    with SessionLocal() as session:
        with pytest.raises(RequestIntakeError):
            submit_request(
                session,
                request_id="TST-INTAKE-BAD1",
                requester_id="L-99",
                raw_content="body",
            )
        session.rollback()
    # 12. no partial state remains
    assert _request_count() == 26


def test_external_requester_rejected_like_any_unknown_member():
    # The seed decision (no synthetic TeamMember for EXTERNAL) holds at the
    # service level too: an unknown requester can never enter intake.
    with SessionLocal() as session:
        with pytest.raises(RequestIntakeError):
            submit_request(
                session,
                request_id="TST-INTAKE-BAD2",
                requester_id="EXTERNAL",
                raw_content="privileged grab attempt",
            )
        session.rollback()
    assert _request_count() == 26


def test_invalid_organisation_rejected():
    with SessionLocal() as session:
        with pytest.raises(RequestIntakeError):
            submit_request(
                session,
                request_id="TST-INTAKE-BAD3",
                requester_id="L-02",
                raw_content="body",
                org_id="ORG-9999",
            )
        session.rollback()
    assert _request_count() == 26


def test_intake_writes_exactly_one_audit_event():
    with SessionLocal() as session:
        request = submit_request(
            session,
            request_id="TST-INTAKE-004",
            requester_id="L-02",
            raw_content="body",
            org_id="ORG-1007",
        )
        session.commit()
        request_id = request.request_id
    try:
        with SessionLocal() as verify:
            events = verify.scalars(
                select(AuditEvent).where(AuditEvent.request_id == request_id)
            ).all()
            assert len(events) == 1
            evt = events[0]
            assert evt.event_type == "intake"
            assert evt.actor_id == "L-02"
            assert evt.detail_reference == f"request:{request_id}"
            assert evt.detail_json == {"org_id": "ORG-1007"}
            assert evt.occurred_at is not None
    finally:
        _cleanup_request(request_id)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def test_classification_sets_type_and_transitions_status():
    with SessionLocal() as session:
        submit_request(
            session,
            request_id="TST-CLASS-001",
            requester_id="L-02",
            raw_content="review the supply agreement",
            org_id="ORG-1007",
        )
        classify_request(
            session, request_id="TST-CLASS-001", request_type="contract_review"
        )
        session.commit()

    try:
        with SessionLocal() as verify:
            row = verify.get(Request, "TST-CLASS-001")
            # 4. correct request_type persistence + lifecycle transition
            assert row.request_type == "contract_review"
            assert row.status == "classified"

            events = verify.scalars(
                select(AuditEvent).where(AuditEvent.request_id == "TST-CLASS-001")
            ).all()
            by_type = {e.event_type: e for e in events}
            assert set(by_type) == {"intake", "classified"}
            assert by_type["classified"].actor_id is None  # system action
            assert by_type["classified"].detail_json == {"request_type": "contract_review"}
    finally:
        _cleanup_request("TST-CLASS-001")


def test_classification_rejects_unsupported_type():
    with SessionLocal() as session:
        submit_request(
            session,
            request_id="TST-CLASS-002",
            requester_id="L-02",
            raw_content="body",
        )
        with pytest.raises(RequestIntakeError):
            classify_request(
                session, request_id="TST-CLASS-002", request_type="data_room_access"
            )
        session.rollback()
        _cleanup_request("TST-CLASS-002")
    # The four documented classification types remain the only vocabulary.
    assert CLASSIFIABLE_REQUEST_TYPES == frozenset(
        {"contract_review", "consultation", "meeting_prep", "obligation_check"}
    )


def test_classification_requires_existing_intake_request():
    with SessionLocal() as session:
        with pytest.raises(RequestIntakeError):
            classify_request(
                session, request_id="TST-CLASS-MISSING", request_type="consultation"
            )
        session.rollback()

    # Lifecycle guard: a request can be classified exactly once.
    with SessionLocal() as session:
        submit_request(
            session,
            request_id="TST-CLASS-003",
            requester_id="L-03",
            raw_content="body",
        )
        classify_request(
            session, request_id="TST-CLASS-003", request_type="consultation"
        )
        with pytest.raises(RequestIntakeError):
            classify_request(
                session, request_id="TST-CLASS-003", request_type="consultation"
            )
        session.rollback()
        _cleanup_request("TST-CLASS-003")


def test_classification_performs_no_authorization_decision():
    with SessionLocal() as session:
        submit_request(
            session,
            request_id="TST-CLASS-004",
            requester_id="L-08",  # valid member, deliberately NOT on ORG-1033
            raw_content="body",
        )
        session.commit()

    try:
        with sql_spy() as statements:
            with SessionLocal() as session:
                classify_request(
                    session, request_id="TST-CLASS-004", request_type="obligation_check"
                )
                session.rollback()

        forbidden = ("matter_assignment", "access_decision")
        touched = [s for s in statements if any(t in s for t in forbidden)]
        assert not touched, f"classification queried authorization tables: {touched}"
    finally:
        _cleanup_request("TST-CLASS-004")


def test_classification_reads_no_documents():
    with SessionLocal() as session:
        submit_request(
            session,
            request_id="TST-CLASS-005",
            requester_id="L-02",
            raw_content="body",
        )
        session.commit()

    try:
        with sql_spy() as statements:
            with SessionLocal() as session:
                classify_request(
                    session, request_id="TST-CLASS-005", request_type="meeting_prep"
                )
                session.rollback()

        document_tables = ("contract", "data_room_file", "review_standard_clause")
        touched = [s for s in statements if any(t in s for t in document_tables)]
        assert not touched, f"classification read documents: {touched}"
    finally:
        _cleanup_request("TST-CLASS-005")


# ---------------------------------------------------------------------------
# Seeded-data fidelity
# ---------------------------------------------------------------------------

def test_seeded_request_represented_correctly():
    source_fields, reason = load_data.parse_request(
        load_data.DATA_DIR / "requests" / "L-C-001.txt"
    )
    assert reason is None

    with SessionLocal() as session:
        row = session.get(Request, "L-C-001")
        assert row is not None
        assert row.requester_id == source_fields["requester_id"] == "L-02"
        assert row.org_id == source_fields["org_id"] == "ORG-1007"
        assert row.request_type == source_fields["request_type"] == "contract_review"
        assert row.status == "intake"
        assert row.created_at == datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert row.raw_content == source_fields["raw_content"]


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def test_seeded_arabic_request_body_preserved():
    source_fields, reason = load_data.parse_request(
        load_data.DATA_DIR / "requests" / "L-C-009.txt"
    )
    assert reason is None
    with SessionLocal() as session:
        row = session.get(Request, "L-C-009")
        assert row.raw_content == source_fields["raw_content"]
        assert ARABIC_RE.search(row.raw_content)