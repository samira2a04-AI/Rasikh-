"""Focused tests for the secure document-retrieval service.

Runs against the seeded local PostgreSQL database. Tests create temporary
AccessDecision rows through the real access-control service and remove them
again; every test also rolls back or cleans up any audit events it produced,
so the seeded dataset is left untouched (enforced by a module-level guard).
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
from contextlib import contextmanager
from pathlib import Path

# Make scripts/ importable so the independent source parser can be reused.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import load_data  # noqa: E402  — scripts/load_data.py

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import func, select

import app.services.document_retrieval as dr_module
from app.database.connection import SessionLocal, engine
from app.models import AccessDecision, AuditEvent, Organisation, TeamMember
from app.services.access_control import record_access_decision
from app.services.document_retrieval import (
    DocumentAccessDenied,
    retrieve_contracts,
    retrieve_contract_clauses,
    retrieve_data_room_files,
    retrieve_review_standard_clauses,
)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


@contextmanager
def recorded_decision(request_id: str, member_id: str, org_id: str):
    """Commit an AccessDecision via the real access-control service.

    The outcome (authorized/unauthorized) follows from the seeded assignment
    data. The row is removed again on exit.
    """
    with SessionLocal() as session:
        decision = record_access_decision(
            session, request_id=request_id, member_id=member_id, org_id=org_id
        )
        session.commit()
        decision_id = decision.access_decision_id
    try:
        yield decision_id
    finally:
        with SessionLocal() as session:
            row = session.get(AccessDecision, decision_id)
            if row is not None:
                session.delete(row)
                session.commit()


def document_retrieved_event_count() -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "document_retrieved")
        ).scalar_one()


@pytest.fixture(scope="module", autouse=True)
def guard_seed_and_audit_baseline():
    """Fail fast if seed data is missing; prove no audit events leak."""
    with SessionLocal() as session:
        for member_id in ("L-02", "L-03", "L-04", "L-05", "L-08", "L-10"):
            assert session.get(TeamMember, member_id) is not None, f"seed missing: {member_id}"
        for org_id in ("ORG-1007", "ORG-1012", "ORG-1028", "ORG-1033", "ORG-1055"):
            assert session.get(Organisation, org_id) is not None, f"seed missing: {org_id}"
    baseline = document_retrieved_event_count()
    yield
    leaked = document_retrieved_event_count() - baseline
    assert leaked == 0, f"{leaked} document_retrieved audit event(s) leaked from tests"


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

def test_authorized_member_retrieves_own_contracts():
    with recorded_decision("L-C-001", "L-02", "ORG-1007"):
        with SessionLocal() as session:
            contracts = retrieve_contracts(
                session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
            )
            contract_ids = sorted(c.contract_id for c in contracts)
            org_ids = {c.org_id for c in contracts}
            session.rollback()  # discard the uncommitted audit event
    assert contract_ids == ["C-01", "C-03"]  # exactly ORG-1007's contracts
    assert org_ids == {"ORG-1007"}  # never another organisation's


def test_unauthorized_member_cannot_retrieve_contracts():
    # L-08 is a valid member but holds no authorised decision for this triple.
    with pytest.raises(DocumentAccessDenied):
        with SessionLocal() as session:
            retrieve_contracts(
                session, request_id="L-C-002", member_id="L-08", org_id="ORG-1007"
            )


def test_missing_access_decision_denies_retrieval():
    # L-05 IS assigned to ORG-1007, but no AccessDecision was ever recorded
    # for this request — the recorded decision is the gate, not the assignment.
    with pytest.raises(DocumentAccessDenied):
        with SessionLocal() as session:
            retrieve_contracts(
                session, request_id="L-C-003", member_id="L-05", org_id="ORG-1007"
            )


def test_unauthorized_access_decision_denies_retrieval():
    # An actually-recorded decision with outcome='unauthorized' must NOT unlock
    # retrieval (the gate requires outcome='authorized').
    with recorded_decision("L-C-002", "L-08", "ORG-1033"):  # records 'unauthorized'
        with pytest.raises(DocumentAccessDenied):
            with SessionLocal() as session:
                retrieve_contracts(
                    session, request_id="L-C-002", member_id="L-08", org_id="ORG-1033"
                )


def test_authorized_member_cannot_retrieve_other_orgs_contracts():
    # Authorised for ORG-1007 only; asking for ORG-1019 fails the exact-triple
    # gate and must not return ORG-1019's contracts.
    with recorded_decision("L-C-001", "L-02", "ORG-1007"):
        with pytest.raises(DocumentAccessDenied):
            with SessionLocal() as session:
                retrieve_contracts(
                    session, request_id="L-C-001", member_id="L-02", org_id="ORG-1019"
                )


# ---------------------------------------------------------------------------
# Contract clauses
# ---------------------------------------------------------------------------

def test_contract_clauses_restricted_through_parent_contract_org():
    with recorded_decision("L-C-001", "L-02", "ORG-1007"):
        # Positive: own contract's clauses come back intact.
        with SessionLocal() as session:
            clauses = retrieve_contract_clauses(
                session,
                request_id="L-C-001",
                member_id="L-02",
                org_id="ORG-1007",
                contract_id="C-01",
            )
            labels = {c.clause_label for c in clauses}
            fields_ok = all(
                c.contract_id == "C-01"
                and c.clause_id is not None
                and c.text
                for c in clauses
            )
            session.rollback()
        assert labels == {"1", "2", "3", "7", "9", "12"}
        assert fields_ok

        # Negative: C-02 belongs to ORG-1012 — denied despite valid clause id.
        with pytest.raises(DocumentAccessDenied):
            with SessionLocal() as session:
                retrieve_contract_clauses(
                    session,
                    request_id="L-C-001",
                    member_id="L-02",
                    org_id="ORG-1007",
                    contract_id="C-02",
                )


# ---------------------------------------------------------------------------
# Data-room files
# ---------------------------------------------------------------------------

def test_authorized_member_retrieves_data_room_files():
    with recorded_decision("L-C-001", "L-02", "ORG-1007"):
        with SessionLocal() as session:
            files = retrieve_data_room_files(
                session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
            )
            file_ids = sorted(f.file_id for f in files)
            session.rollback()
    assert file_ids == ["DR-01"]


def test_unauthorized_member_cannot_retrieve_data_room_files():
    with pytest.raises(DocumentAccessDenied):
        with SessionLocal() as session:
            retrieve_data_room_files(
                session, request_id="L-C-002", member_id="L-08", org_id="ORG-1007"
            )


def test_dr04_privileged_flag_preserved():
    # L-C-017's requester L-03 is a firm-wide partner on ORG-1055 (Manar).
    with recorded_decision("L-C-017", "L-03", "ORG-1055"):
        with SessionLocal() as session:
            files = retrieve_data_room_files(
                session, request_id="L-C-017", member_id="L-03", org_id="ORG-1055"
            )
            flags = {f.file_id: f.privileged for f in files}
            session.rollback()
    assert flags == {"DR-04": True}


def test_unauthorized_member_cannot_retrieve_dr04():
    # L-05 IS on the Manar matter team, but with no recorded authorised
    # decision the privileged file is unreachable — the recorded decision,
    # not team membership alone, opens the door.
    with pytest.raises(DocumentAccessDenied):
        with SessionLocal() as session:
            retrieve_data_room_files(
                session, request_id="L-C-010", member_id="L-05", org_id="ORG-1055"
            )


# ---------------------------------------------------------------------------
# Arabic integrity
# ---------------------------------------------------------------------------

def test_arabic_clauses_returned_without_corruption():
    source = load_data.parse_contract(load_data.DATA_DIR / "contracts" / "C-09_Hijaz_Supply_AR.txt")
    expected = {
        cl["clause_label"]: cl["text"] for cl in source["clauses"] if cl["clause_label"] is not None
    }

    with recorded_decision("L-C-009", "L-10", "ORG-1028"):
        with SessionLocal() as session:
            clauses = retrieve_contract_clauses(
                session,
                request_id="L-C-009",
                member_id="L-10",
                org_id="ORG-1028",
                contract_id="C-09",
            )
            actual = {c.clause_label: c.text for c in clauses if c.clause_label is not None}
            session.rollback()
    assert actual == expected  # byte-for-byte identical to the source file text
    assert actual and all(ARABIC_RE.search(t) for t in actual.values())


# ---------------------------------------------------------------------------
# Review-standard clauses
# ---------------------------------------------------------------------------

def test_review_standard_clauses_follow_authorization_semantics():
    # Without a recorded authorised decision: denied (architecture §6 — the
    # standard's USE requires the calling request to have passed the check).
    with pytest.raises(DocumentAccessDenied):
        with SessionLocal() as session:
            retrieve_review_standard_clauses(
                session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
            )

    # With one: the full corpus is available, with deterministic filters.
    with recorded_decision("L-C-001", "L-02", "ORG-1007"):
        with SessionLocal() as session:
            all_clauses = retrieve_review_standard_clauses(
                session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
            )
            threshold_clause = retrieve_review_standard_clauses(
                session,
                request_id="L-C-001",
                member_id="L-02",
                org_id="ORG-1007",
                clause_number="6.2",
            )
            total_count = len(all_clauses)
            threshold_category = threshold_clause[0].category
            session.rollback()
    assert total_count == 31
    assert threshold_category == "obligation_threshold"


# ---------------------------------------------------------------------------
# Failure atomicity, content boundaries, no-AI guarantees
# ---------------------------------------------------------------------------

def test_failed_retrieval_returns_no_partial_data_and_no_false_audit():
    baseline = document_retrieved_event_count()
    with pytest.raises(DocumentAccessDenied):
        with SessionLocal() as session:
            retrieve_contracts(
                session, request_id="L-C-004", member_id="L-07", org_id="ORG-1033"
            )
    with pytest.raises(DocumentAccessDenied):
        with SessionLocal() as session:
            retrieve_contract_clauses(
                session,
                request_id="L-C-004",
                member_id="L-07",
                org_id="ORG-1033",
                contract_id="C-04",
            )
    # Nothing was committed: no document data out, no document_retrieved event.
    assert document_retrieved_event_count() == baseline


def test_retrieval_never_reads_request_raw_content():
    statements: list[str] = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    sa_event.listen(engine, "before_cursor_execute", spy)
    try:
        with recorded_decision("L-C-001", "L-02", "ORG-1007"):
            with SessionLocal() as session:
                retrieve_contracts(
                    session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
                )
                retrieve_contract_clauses(
                    session,
                    request_id="L-C-001",
                    member_id="L-02",
                    org_id="ORG-1007",
                    contract_id="C-01",
                )
                retrieve_data_room_files(
                    session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
                )
                retrieve_review_standard_clauses(
                    session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
                )
                session.rollback()
    finally:
        sa_event.remove(engine, "before_cursor_execute", spy)

    assert statements, "retrieval should issue SQL"
    assert not any(re.search(r"from\s+request\b", s) for s in statements), (
        "the request table was queried during retrieval"
    )
    assert not any("raw_content" in s for s in statements), (
        "raw_content was read during retrieval"
    )


def test_no_llm_or_ai_component_involved():
    """The retrieval module may import only SQLAlchemy and project code."""
    tree = ast.parse(inspect.getsource(dr_module))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0].lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0].lower())

    assert imported_roots <= {"sqlalchemy", "app", "__future__"}, (
        f"unexpected imports: {imported_roots}"
    )
    banned = {
        "openai",
        "anthropic",
        "transformers",
        "langchain",
        "llama_index",
        "httpx",
        "requests",
        "urllib",
        "socket",
    }
    assert imported_roots.isdisjoint(banned)


# ---------------------------------------------------------------------------
# Audit behaviour
# ---------------------------------------------------------------------------

def test_successful_retrieval_writes_document_retrieved_audit_event():
    with recorded_decision("L-C-001", "L-02", "ORG-1007"):
        with SessionLocal() as session:
            retrieve_contracts(
                session, request_id="L-C-001", member_id="L-02", org_id="ORG-1007"
            )
            session.commit()  # persist the append-only audit event

        try:
            with SessionLocal() as verify:
                events = verify.scalars(
                    select(AuditEvent).where(
                        AuditEvent.request_id == "L-C-001",
                        AuditEvent.event_type == "document_retrieved",
                    )
                ).all()
                assert len(events) == 1
                evt = events[0]
                assert evt.actor_id == "L-02"
                assert evt.detail_reference == "contract:C-01,C-03"
                assert evt.detail_json == {"org_id": "ORG-1007", "count": 2}
                assert evt.occurred_at is not None
        finally:
            with SessionLocal() as cleanup:
                for evt in cleanup.scalars(
                    select(AuditEvent).where(
                        AuditEvent.request_id == "L-C-001",
                        AuditEvent.event_type == "document_retrieved",
                    )
                ):
                    cleanup.delete(evt)
                cleanup.commit()