"""Focused tests for the access-control service (app/services/access_control.py).

These tests run against the seeded local PostgreSQL database. Persistence
tests commit an AccessDecision row and delete it again in a ``finally``
block, so the seeded dataset is left untouched.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event

from app.database.connection import SessionLocal, engine
from app.models import AccessDecision, Organisation, TeamMember
from app.services.access_control import (
    AccessControlInputError,
    check_access,
    record_access_decision,
)


@pytest.fixture(scope="module", autouse=True)
def require_seed():
    """Fail fast with a clear message if expected seed rows are missing."""
    with SessionLocal() as session:
        assert session.get(TeamMember, "L-01") is not None, "seed missing: L-01"
        assert session.get(TeamMember, "L-04") is not None, "seed missing: L-04"
        assert session.get(TeamMember, "L-08") is not None, "seed missing: L-08"
        assert session.get(Organisation, "ORG-1007") is not None, "seed missing: ORG-1007"
        assert session.get(Organisation, "ORG-1033") is not None, "seed missing: ORG-1033"
        assert session.get(Organisation, "ORG-1072") is not None, "seed missing: ORG-1072"


def test_authorized_assigned_member():
    """L-04 is explicitly assigned to ORG-1007 in the seed data."""
    with SessionLocal() as session:
        result = check_access(session, member_id="L-04", org_id="ORG-1007")
    assert result.authorized is True
    assert result.member_id == "L-04"
    assert result.org_id == "ORG-1007"
    assert result.basis == "matter_assignment"


def test_unauthorized_member():
    """L-08's assignments are ORG-1007/ORG-1012 only — not ORG-1033."""
    with SessionLocal() as session:
        result = check_access(session, member_id="L-08", org_id="ORG-1033")
    assert result.authorized is False
    assert result.basis == "no_matter_assignment"


def test_firm_wide_partner():
    """Partners are authorized for every organisation via materialised rows."""
    with SessionLocal() as session:
        for org_id in ("ORG-1001", "ORG-1055", "ORG-1072"):
            result = check_access(session, member_id="L-01", org_id=org_id)
            assert result.authorized is True, org_id
            assert result.basis == "matter_assignment"


def test_unknown_member():
    with SessionLocal() as session:
        result = check_access(session, member_id="L-99", org_id="ORG-1007")
    assert result.authorized is False
    assert result.basis == "unknown_member"


def test_unknown_organisation():
    with SessionLocal() as session:
        result = check_access(session, member_id="L-02", org_id="ORG-9999")
    assert result.authorized is False
    assert result.basis == "unknown_organisation"


def _persist_and_verify(request_id: str, member_id: str, org_id: str, outcome: str) -> None:
    """Record a decision, verify it survives a real COMMIT, then remove it."""
    with SessionLocal() as session:
        decision = record_access_decision(
            session, request_id=request_id, member_id=member_id, org_id=org_id
        )
        session.commit()
        decision_id = decision.access_decision_id

    try:
        with SessionLocal() as verify_session:
            row = verify_session.get(AccessDecision, decision_id)
            assert row is not None, "AccessDecision row was not persisted"
            assert row.request_id == request_id
            assert row.member_id == member_id
            assert row.org_id == org_id
            assert row.outcome == outcome
            assert row.decided_at is not None
            if outcome == "authorized":
                assert row.basis == "matter_assignment"
            else:
                assert row.basis == "no_matter_assignment"
    finally:
        with SessionLocal() as cleanup:
            row = cleanup.get(AccessDecision, decision_id)
            if row is not None:
                cleanup.delete(row)
                cleanup.commit()


def test_authorized_decision_persisted():
    _persist_and_verify("L-C-001", "L-02", "ORG-1007", "authorized")


def test_unauthorized_decision_persisted():
    _persist_and_verify("L-C-002", "L-08", "ORG-1033", "unauthorized")


def test_record_rejects_unknown_member_without_persisting():
    with SessionLocal() as session:
        with pytest.raises(AccessControlInputError):
            record_access_decision(
                session, request_id="L-C-001", member_id="L-99", org_id="ORG-1007"
            )
        session.rollback()
        # Nothing was added to the session by the failed call.
        assert not [obj for obj in session.new]


def test_record_rejects_unknown_organisation_without_persisting():
    with SessionLocal() as session:
        with pytest.raises(AccessControlInputError):
            record_access_decision(
                session, request_id="L-C-001", member_id="L-02", org_id="ORG-9999"
            )
        session.rollback()
        assert not [obj for obj in session.new]


def test_check_access_never_touches_document_tables():
    """SEC-002: the access check must not query contract/data-room tables."""
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        with SessionLocal() as session:
            check_access(session, member_id="L-01", org_id="ORG-1007")
            check_access(session, member_id="L-08", org_id="ORG-1033")
            check_access(session, member_id="L-99", org_id="ORG-1007")
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert statements, "expected at least one SQL statement from check_access"
    document_queries = [
        s for s in statements if "contract" in s or "data_room_file" in s
    ]
    assert not document_queries, f"document tables queried during access check: {document_queries}"