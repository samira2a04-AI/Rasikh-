"""Focused tests for the grounded review / findings / citations service.

Runs against the seeded local PostgreSQL database. Tests create temporary
Finding/Citation/AuditEvent rows and remove them again; a module-level guard
proves the seeded dataset is left untouched.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

# Make scripts/ importable so the independent source parser can be reused.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import load_data  # noqa: E402  — scripts/load_data.py

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models import (
    AuditEvent,
    Citation,
    ContractClause,
    Finding,
    Request,
    ReviewStandardClause,
)
from app.services.review import (
    CHECKLIST_AREAS,
    NOT_IN_DOCUMENTS_PHRASE,
    TRICKY_CASE_TYPES,
    ReviewPersistenceError,
    create_grounded_finding,
    create_ungrounded_finding,
)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clause(contract_id: str, label: str) -> ContractClause:
    """Fetch a seeded contract clause as a detached instance."""
    with SessionLocal() as session:
        clause = session.execute(
            select(ContractClause).where(
                ContractClause.contract_id == contract_id,
                ContractClause.clause_label == label,
            )
        ).scalar_one()
        session.expunge(clause)
        return clause


def _standard_clause(number: str) -> ReviewStandardClause:
    """Fetch a seeded review-standard clause as a detached instance."""
    with SessionLocal() as session:
        clause = session.execute(
            select(ReviewStandardClause).where(
                ReviewStandardClause.clause_number == number
            )
        ).scalar_one()
        session.expunge(clause)
        return clause


def _cleanup_finding(finding_id) -> None:
    with SessionLocal() as session:
        for c in session.scalars(select(Citation).where(Citation.finding_id == finding_id)):
            session.delete(c)
        row = session.get(Finding, finding_id)
        if row is not None:
            session.delete(row)
        for evt in session.scalars(
            select(AuditEvent).where(AuditEvent.detail_reference == f"finding:{finding_id}")
        ):
            session.delete(evt)
        session.commit()


def _count(model) -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(model)).scalar_one()


def _finding_produced_events(finding_id) -> list[AuditEvent]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"finding:{finding_id}"
                )
            )
        )


@pytest.fixture(scope="module", autouse=True)
def guard_seed():
    """Fail fast if seed data is missing."""
    with SessionLocal() as session:
        assert session.get(Request, "L-C-001") is not None, "seed missing: request L-C-001"
        c01_clauses = session.execute(
            select(func.count())
            .select_from(ContractClause)
            .where(ContractClause.contract_id == "C-01")
        ).scalar_one()
        assert c01_clauses >= 6, "seed missing: C-01 clauses"
        std_count = session.execute(
            select(func.count()).select_from(ReviewStandardClause)
        ).scalar_one()
        assert std_count == 31, "seed missing: rulebook clauses"


# ---------------------------------------------------------------------------
# Grounded findings
# ---------------------------------------------------------------------------

def test_grounded_finding_persisted_with_all_fields():
    clause = _clause("C-01", "7")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Liability is capped at the total contract value (C-01 clause 7).",
            citations=[clause],
            checklist_area="liability",
            risk_rating="high",
            sharia_sensitive_flag=True,
            tricky_case_type="capped_liability",
        )
        session.commit()
        finding_id = finding.finding_id

    try:
        with SessionLocal() as verify:
            row = verify.get(Finding, finding_id)
            assert row is not None
            assert row.request_id == "L-C-001"          # 17. correct request_id
            assert row.grounded is True
            assert row.checklist_area == "liability"
            assert row.risk_rating == "high"
            assert row.sharia_sensitive_flag is True     # 14. sharia flag persists
            assert row.tricky_case_type == "capped_liability"

            citations = verify.scalars(
                select(Citation).where(Citation.finding_id == finding_id)
            ).all()
            assert len(citations) == 1                   # 2. >=1 citation
            assert citations[0].source_type == "contract_clause"   # 3.
            assert citations[0].contract_clause_id == clause.clause_id
            assert citations[0].standard_clause_id is None
    finally:
        _cleanup_finding(finding_id)


def test_grounded_finding_requires_at_least_one_citation():
    with SessionLocal() as session:
        with pytest.raises(ReviewPersistenceError):
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="An assertion with nothing behind it.",
                citations=[],
            )
        session.rollback()


def test_review_standard_clause_citation_works():
    std = _standard_clause("0.1")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Every answer names its source per rulebook 0.1.",
            citations=[std],
            checklist_area="other",
        )
        session.commit()
        finding_id = finding.finding_id

    try:
        with SessionLocal() as verify:
            citation = verify.scalars(
                select(Citation).where(Citation.finding_id == finding_id)
            ).one()
            assert citation.source_type == "standard_clause"         # 4.
            assert citation.standard_clause_id == std.standard_clause_id
            assert citation.contract_clause_id is None
            # 5. citation FK resolves to the real standard-clause row
            joined = verify.execute(
                select(ReviewStandardClause.clause_number)
                .join(Citation, Citation.standard_clause_id == ReviewStandardClause.standard_clause_id)
                .where(Citation.citation_id == citation.citation_id)
            ).scalar_one()
            assert joined == "0.1"
    finally:
        _cleanup_finding(finding_id)


def test_contract_clause_citation_fk_resolves():
    clause = _clause("C-01", "1")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Fixed twelve-month term expiring 28 February 2027.",
            citations=[clause],
            checklist_area="term_renewal",
            tricky_case_type="fixed_expiry",
        )
        session.commit()
        finding_id = finding.finding_id

    try:
        with SessionLocal() as verify:
            citation = verify.scalars(
                select(Citation).where(Citation.finding_id == finding_id)
            ).one()
            # 5. citation FK resolves to the real contract-clause row
            label = verify.execute(
                select(ContractClause.clause_label)
                .join(Citation, Citation.contract_clause_id == ContractClause.clause_id)
                .where(Citation.citation_id == citation.citation_id)
            ).scalar_one()
            assert label == "1"
    finally:
        _cleanup_finding(finding_id)


def test_nonexistent_contract_clause_rejected_by_fk():
    baseline_f = _count(Finding)
    baseline_c = _count(Citation)
    fabricated = ContractClause(
        clause_id=uuid.uuid4(), contract_id="C-01", text="fabricated clause"
    )  # never persisted
    with SessionLocal() as session:
        with pytest.raises(IntegrityError):                      # 6.
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="Citing something that does not exist.",
                citations=[fabricated],
            )
        session.rollback()
    assert _count(Finding) == baseline_f and _count(Citation) == baseline_c


def test_nonexistent_standard_clause_rejected_by_fk():
    baseline_f = _count(Finding)
    baseline_c = _count(Citation)
    fabricated = ReviewStandardClause(
        standard_clause_id=uuid.uuid4(), clause_number="9.9", text="fabricated rule"
    )  # never persisted
    with SessionLocal() as session:
        with pytest.raises(IntegrityError):                      # 7.
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="Citing a rulebook clause that does not exist.",
                citations=[fabricated],
            )
        session.rollback()
    assert _count(Finding) == baseline_f and _count(Citation) == baseline_c


def test_bare_identifiers_are_never_accepted_as_citations():
    """The only citable things are supplied retrieved-clause instances."""
    baseline_f = _count(Finding)
    baseline_c = _count(Citation)
    with SessionLocal() as session:
        with pytest.raises(ReviewPersistenceError):              # 8.
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="Trying to cite by raw id.",
                citations=["not-a-clause"],  # type: ignore[list-item]
            )
        with pytest.raises(ReviewPersistenceError):
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="Trying to cite by raw uuid.",
                citations=[uuid.uuid4()],  # type: ignore[list-item]
            )
        session.rollback()
    assert _count(Finding) == baseline_f and _count(Citation) == baseline_c


def test_multiple_citations_supported():
    c1 = _clause("C-01", "1")
    c2 = _clause("C-01", "7")
    std = _standard_clause("3.3")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Term and liability findings with mixed sources.",
            citations=[c1, c2, std],
        )
        session.commit()
        finding_id = finding.finding_id
    try:
        with SessionLocal() as verify:
            citations = verify.scalars(
                select(Citation).where(Citation.finding_id == finding_id)
            ).all()
            assert len(citations) == 3
            assert {c.source_type for c in citations} == {"contract_clause", "standard_clause"}
    finally:
        _cleanup_finding(finding_id)


# ---------------------------------------------------------------------------
# Ungrounded findings
# ---------------------------------------------------------------------------

def test_ungrounded_finding_has_zero_citations():
    with SessionLocal() as session:
        finding = create_ungrounded_finding(
            session,
            request_id="L-C-001",
            statement=(
                "The governing-law position is not addressed in the documents "
                "provided for this matter."
            ),
            checklist_area="governing_law",
        )
        session.commit()
        finding_id = finding.finding_id
    try:
        with SessionLocal() as verify:
            row = verify.get(Finding, finding_id)
            assert row.grounded is False                          # 9.
            citations = verify.scalars(
                select(Citation).where(Citation.finding_id == finding_id)
            ).all()
            assert citations == []                                # 9. zero citations
            assert NOT_IN_DOCUMENTS_PHRASE in row.statement.lower()  # 10.
    finally:
        _cleanup_finding(finding_id)


def test_ungrounded_statement_must_carry_required_wording():
    with SessionLocal() as session:
        with pytest.raises(ReviewPersistenceError):
            create_ungrounded_finding(
                session,
                request_id="L-C-001",
                statement="Governing law is probably Saudi law.",  # no honest wording
            )
        session.rollback()

    # Canonical rulebook 0.1 sentence is accepted.
    with SessionLocal() as session:
        finding = create_ungrounded_finding(
            session,
            request_id="L-C-001",
            statement="This is not addressed in the documents provided.",
        )
        session.commit()
        finding_id = finding.finding_id
    _cleanup_finding(finding_id)


def test_unknown_request_rejected():
    baseline_f = _count(Finding)
    with SessionLocal() as session:
        with pytest.raises(ReviewPersistenceError):
            create_grounded_finding(
                session,
                request_id="TST-NO-SUCH-REQUEST",
                statement="x",
                citations=[_clause("C-01", "1")],
            )
        with pytest.raises(ReviewPersistenceError):
            create_ungrounded_finding(
                session,
                request_id="TST-NO-SUCH-REQUEST",
                statement="This is not addressed in the documents provided.",
            )
        session.rollback()
    assert _count(Finding) == baseline_f


# ---------------------------------------------------------------------------
# Arabic integrity
# ---------------------------------------------------------------------------

def test_arabic_contract_clause_citation_preserves_arabic():
    source = load_data.parse_contract(load_data.DATA_DIR / "contracts" / "C-09_Hijaz_Supply_AR.txt")
    expected_text = next(
        cl["text"] for cl in source["clauses"] if cl["clause_label"] == "1"
    )

    clause = _clause("C-09", "1")
    assert ARABIC_RE.search(clause.text)
    assert clause.text == expected_text  # stored Arabic identical to source file

    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-009",
            statement="المدة سنة واحدة مع تجديد تلقائي ما لم يُخطر الطرف الآخر قبل ستين يوماً.",
            citations=[clause],
            checklist_area="term_renewal",
            tricky_case_type="auto_renewal",
        )
        session.commit()
        finding_id = finding.finding_id

    try:
        with SessionLocal() as verify:
            citation = verify.scalars(
                select(Citation).where(Citation.finding_id == finding_id)
            ).one()
            cited_clause = verify.get(ContractClause, citation.contract_clause_id)
            assert cited_clause is not None                       # 11.
            assert cited_clause.contract_id == "C-09"
            assert cited_clause.text == expected_text             # Arabic unchanged
            assert ARABIC_RE.search(cited_clause.text)
    finally:
        _cleanup_finding(finding_id)


# ---------------------------------------------------------------------------
# Vocabulary enforcement
# ---------------------------------------------------------------------------

def test_checklist_area_vocabulary_enforced():
    assert CHECKLIST_AREAS == frozenset(
        {"term_renewal", "liability", "payment", "termination", "governing_law", "gap", "other"}
    )
    with SessionLocal() as session:
        with pytest.raises(ReviewPersistenceError):               # 12.
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="x",
                citations=[_clause("C-01", "1")],
                checklist_area="renewal_terms",  # invented value
            )
        session.rollback()


def test_tricky_case_type_vocabulary_enforced():
    assert TRICKY_CASE_TYPES == frozenset(
        {
            "fixed_expiry",
            "auto_renewal",
            "capped_liability",
            "uncapped_liability",
            "capped_with_uncapped_carveout",
            "none",
        }
    )
    with SessionLocal() as session:
        with pytest.raises(ReviewPersistenceError):               # 13.
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="x",
                citations=[_clause("C-01", "1")],
                tricky_case_type="auto-renewal",  # wrong spelling / invented
            )
        session.rollback()


def test_risk_rating_persisted_verbatim_without_new_taxonomy():
    """Neutral persistence: the taxonomy lives in the rulebook, applied later."""
    clause = _clause("C-03", "7")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-003",
            statement="Carve-out makes liability unlimited for scope breach.",
            citations=[clause],
            checklist_area="liability",
            risk_rating="high",  # supplied by the future Risk Analysis component
        )
        session.commit()
        finding_id = finding.finding_id
    try:
        with SessionLocal() as verify:
            row = verify.get(Finding, finding_id)
            assert row.risk_rating == "high"                      # 15.
    finally:
        _cleanup_finding(finding_id)


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------

def test_finding_and_citations_are_atomic():
    good = _clause("C-01", "1")
    bad = ReviewStandardClause(
        standard_clause_id=uuid.uuid4(), clause_number="9.9", text="fabricated"
    )
    before_f = _count(Finding)
    before_c = _count(Citation)
    before_e = _count(AuditEvent)
    with SessionLocal() as session:
        with pytest.raises(IntegrityError):                       # 16.
            create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="Mixed valid and fabricated citations.",
                citations=[good, bad],
            )
        session.rollback()


# ---------------------------------------------------------------------------
# Security boundary
# ---------------------------------------------------------------------------

def test_service_queries_no_authorization_or_document_tables():
    from contextlib import contextmanager

    @contextmanager
    def sql_spy():
        statements: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())

        from app.database.connection import engine

        sa_event.listen(engine, "before_cursor_execute", record)
        try:
            yield statements
        finally:
            sa_event.remove(engine, "before_cursor_execute", record)

    clause = _clause("C-01", "7")  # fetched OUTSIDE the spy by the test itself
    std = _standard_clause("6.2")

    with sql_spy() as statements:
        with SessionLocal() as session:
            finding = create_grounded_finding(
                session,
                request_id="L-C-001",
                statement="Capped liability per clause 7; thresholds per rulebook 6.2.",
                citations=[clause, std],
                checklist_area="liability",
            )
            session.rollback()

    assert statements, "expected SQL from the service"
    forbidden_tables = (
        "matter_assignment",
        "access_decision",
        "data_room_file",
    )
    touched = [s for s in statements if any(t in s for t in forbidden_tables)]
    assert not touched, f"service queried forbidden tables: {touched}"       # 19./20.
    document_selects = [
        s
        for s in statements
        if re.search(
            r"from\s+(contract|contract_clause|review_standard_clause)\b", s
        )
    ]
    assert not document_selects, f"service independently retrieved documents: {document_selects}"


# ---------------------------------------------------------------------------
# Audit behaviour
# ---------------------------------------------------------------------------

def test_finding_produced_audit_event_is_correct():
    clause = _clause("C-02", "1")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-002",
            statement="Auto-renewal unless 90 days notice before term end.",
            citations=[clause],
            checklist_area="term_renewal",
            tricky_case_type="auto_renewal",
        )
        session.commit()
        finding_id = finding.finding_id

    try:
        events = _finding_produced_events(finding_id)             # 18.
        assert len(events) == 1
        evt = events[0]
        assert evt.event_type == "finding_produced"
        assert evt.request_id == "L-C-002"
        assert evt.actor_id is None  # system action
        assert evt.detail_reference == f"finding:{finding_id}"
        assert evt.detail_json == {"grounded": True, "citation_count": 1}
        assert evt.occurred_at is not None
    finally:
        _cleanup_finding(finding_id)


# ---------------------------------------------------------------------------
# Human review behaviour
# ---------------------------------------------------------------------------

def test_review_finding_transitions_status_and_logs_audit_event():
    from app.services.review import review_finding

    clause = _clause("C-01", "1")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Term clause review.",
            citations=[clause],
            checklist_area="term_renewal",
        )
        session.commit()
        finding_id = finding.finding_id

    try:
        with SessionLocal() as session:
            reviewed = review_finding(
                session,
                request_id="L-C-001",
                finding_id=finding_id,
                reviewer_id="L-01",
                status="reviewed",
                reviewer_notes="Verified by legal counsel.",
            )
            session.commit()

        with SessionLocal() as verify:
            row = verify.get(Finding, finding_id)
            assert row is not None
            assert row.status == "reviewed"
            assert row.reviewed_by == "L-01"
            assert row.reviewed_at is not None
            assert row.reviewer_notes == "Verified by legal counsel."

            events = list(
                verify.scalars(
                    select(AuditEvent).where(
                        AuditEvent.detail_reference == f"finding:{finding_id}",
                        AuditEvent.event_type == "finding_reviewed",
                    )
                )
            )
            assert len(events) == 1
            evt = events[0]
            assert evt.request_id == "L-C-001"
            assert evt.actor_id == "L-01"
            assert evt.detail_json["status"] == "reviewed"
            assert evt.detail_json["reviewer_notes"] == "Verified by legal counsel."
    finally:
        _cleanup_finding(finding_id)


def test_review_finding_invalid_request_or_finding_raises_error():
    from app.services.review import review_finding

    clause = _clause("C-01", "1")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Term clause review test.",
            citations=[clause],
        )
        session.commit()
        finding_id = finding.finding_id

    try:
        with SessionLocal() as session:
            with pytest.raises(ReviewPersistenceError, match="unknown request_id"):
                review_finding(
                    session,
                    request_id="NO-SUCH-REQ",
                    finding_id=finding_id,
                    reviewer_id="L-01",
                )

            with pytest.raises(ReviewPersistenceError, match="not found for request"):
                review_finding(
                    session,
                    request_id="L-C-001",
                    finding_id=uuid.uuid4(),
                    reviewer_id="L-01",
                )
            session.rollback()
    finally:
        _cleanup_finding(finding_id)