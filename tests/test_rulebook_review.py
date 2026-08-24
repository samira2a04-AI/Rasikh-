"""Focused tests for the rulebook-driven review service.

Each test supplies clause instances exactly as the authorised retrieval layer
would, runs ``review_contract``, and asserts the produced Findings against
the rulebook definitions and the answer_key ground truth. Field values are
snapshotted inside the session (before commit/rollback expires the ORM
objects). All created rows are cleaned up; a module-level guard proves
nothing leaks.
"""

from __future__ import annotations

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

from app.database.connection import SessionLocal, engine
from app.models import (
    AuditEvent,
    Citation,
    ContractClause,
    Finding,
    ReviewStandardClause,
)
from app.services.rulebook_review import (
    RiskFramework,
    derive_risk_framework,
    review_contract,
)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
NOT_IN_DOCS_PHRASE = "not addressed in the documents"

ALL_RULEBOOK = [
    "0.1", "0.2", "0.3", "0.4", "0.5", "0.6",
    "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8",
    "3.1", "3.2", "3.3", "3.4",
    "4.1", "4.2", "4.3", "4.4",
    "5.1", "5.2", "5.3", "5.4", "5.5",
    "6.1", "6.2", "6.3", "6.4",
]


# ---------------------------------------------------------------------------
# Helpers (test-side stand-ins for the retrieval layer's output)
# ---------------------------------------------------------------------------

def _clauses_for(contract_id: str) -> list[ContractClause]:
    """All seeded clauses of a contract, detached — as retrieval would return."""
    with SessionLocal() as session:
        clauses = session.scalars(
            select(ContractClause)
            .where(ContractClause.contract_id == contract_id)
            .order_by(ContractClause.clause_label)
        ).all()
        for c in clauses:
            session.expunge(c)
        return list(clauses)


def _std_clauses(*numbers: str) -> list[ReviewStandardClause]:
    with SessionLocal() as session:
        clauses = session.scalars(
            select(ReviewStandardClause).where(
                ReviewStandardClause.clause_number.in_(numbers)
            )
        ).all()
        for c in clauses:
            session.expunge(c)
        return list(clauses)


def _run_review(
    request_id: str,
    contract_clauses: list[ContractClause],
    standard_clauses: list[ReviewStandardClause],
    *,
    commit: bool = False,
) -> list[dict]:
    """Run a review and return plain-value snapshots of the findings."""
    with SessionLocal() as session:
        findings = review_contract(
            session,
            request_id=request_id,
            contract_clauses=contract_clauses,
            standard_clauses=standard_clauses,
        )
        snap = [
            {
                "id": f.finding_id,
                "area": f.checklist_area,
                "tricky": f.tricky_case_type,
                "risk": f.risk_rating,
                "grounded": f.grounded,
                "sharia": f.sharia_sensitive_flag,
                "statement": f.statement,
            }
            for f in findings
        ]
        if commit:
            session.commit()
        else:
            session.rollback()
    return snap


def _cleanup_finding_ids(finding_ids) -> None:
    with SessionLocal() as session:
        for fid in finding_ids:
            for c in session.scalars(
                select(Citation).where(Citation.finding_id == fid)
            ):
                session.delete(c)
            row = session.get(Finding, fid)
            if row is not None:
                session.delete(row)
            for evt in session.scalars(
                select(AuditEvent).where(
                    AuditEvent.detail_reference == f"finding:{fid}"
                )
            ):
                session.delete(evt)
        session.commit()


def _count(model) -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(model)).scalar_one()


@pytest.fixture(scope="module", autouse=True)
def guard_seed_and_counts():
    """Fail fast if seed data is missing; prove no rows leak from tests."""
    with SessionLocal() as session:
        n_c01 = session.execute(
            select(func.count())
            .select_from(ContractClause)
            .where(ContractClause.contract_id == "C-01")
        ).scalar_one()
        assert n_c01 >= 6, "seed missing: C-01 clauses"
        std_n = session.execute(
            select(func.count()).select_from(ReviewStandardClause)
        ).scalar_one()
        assert std_n == 31, "seed missing: rulebook clauses"

    baseline_f = _count(Finding)
    baseline_c = _count(Citation)
    baseline_e = _count(AuditEvent)
    yield
    assert _count(Finding) == baseline_f, "test leaked Finding rows"
    assert _count(Citation) == baseline_c, "test leaked Citation rows"
    assert _count(AuditEvent) == baseline_e, "test leaked AuditEvent rows"


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
# Tricky pair 1: fixed expiry vs auto-renewal (rulebook 1.1)
# ---------------------------------------------------------------------------

def test_fixed_expiry_classification_c01():
    snap = _run_review("L-C-001", _clauses_for("C-01"), _std_clauses(*ALL_RULEBOOK))
    try:
        term = [f for f in snap if f["area"] == "term_renewal"]
        assert len(term) == 1
        assert term[0]["tricky"] == "fixed_expiry"             # 1.
        assert term[0]["risk"] == "low"                        # from rulebook 3.3
        assert term[0]["grounded"] is True
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


def test_auto_renewal_classification_c02():
    snap = _run_review("L-C-002", _clauses_for("C-02"), _std_clauses(*ALL_RULEBOOK))
    try:
        term = [f for f in snap if f["area"] == "term_renewal"]
        assert len(term) == 1
        assert term[0]["tricky"] == "auto_renewal"             # 2.
        assert "90 days" in term[0]["statement"]               # notice window reported
        assert term[0]["risk"] == "medium"                     # 90 > 30-day threshold (3.2)
        assert term[0]["grounded"] is True
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


# ---------------------------------------------------------------------------
# Tricky pairs 2/3: capped / uncapped / carve-out (rulebook 1.2)
# ---------------------------------------------------------------------------

def test_capped_liability_c04_low_risk():
    snap = _run_review("L-C-004", _clauses_for("C-04"), _std_clauses(*ALL_RULEBOOK))
    try:
        liab = [f for f in snap if f["area"] == "liability"]
        assert len(liab) == 1
        assert liab[0]["tricky"] == "capped_liability"         # 3.
        assert liab[0]["risk"] == "low"                        # cleanly capped at value (3.3)
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


def test_uncapped_liability_c05_high_risk():
    snap = _run_review("L-C-005", _clauses_for("C-05"), _std_clauses(*ALL_RULEBOOK))
    try:
        liab = [f for f in snap if f["area"] == "liability"]
        assert len(liab) == 1
        assert liab[0]["tricky"] == "uncapped_liability"       # 4.
        assert liab[0]["risk"] == "high"                       # 3.1
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


def test_capped_with_uncapped_carveout_c03_high_risk():
    snap = _run_review("L-C-003", _clauses_for("C-03"), _std_clauses(*ALL_RULEBOOK))
    try:
        liab = [f for f in snap if f["area"] == "liability"]
        kinds = {f["tricky"] for f in liab}
        assert kinds == {"capped_with_uncapped_carveout", "uncapped_liability"}
        carveout = next(f for f in liab if f["tricky"] == "capped_with_uncapped_carveout")
        assert carveout["risk"] == "high"                      # 5. reported uncapped, not capped
        assert "not capped" in carveout["statement"]           # FR-021 distinction stated
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


# ---------------------------------------------------------------------------
# Missing essentials (rulebook 1.7/1.8)
# ---------------------------------------------------------------------------

def test_missing_governing_law_and_signature_gaps_c06():
    snap = _run_review("L-C-006", _clauses_for("C-06"), _std_clauses(*ALL_RULEBOOK))
    try:
        gaps = [f for f in snap if f["area"] == "gap"]         # 6.
        assert any("governing-law clause" in f["statement"] for f in gaps)
        assert any("signature block" in f["statement"] for f in gaps)
        assert any("liability position" in f["statement"] for f in gaps)  # C-06 has none
        for g in gaps:
            assert g["grounded"] is False                      # 14. ungrounded gaps
            assert NOT_IN_DOCS_PHRASE in g["statement"].lower()
            assert g["tricky"] is None
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


# ---------------------------------------------------------------------------
# Sharia-sensitive constructs (rulebook 4.1/4.3/4.4)
# ---------------------------------------------------------------------------

def test_sharia_interest_and_penalty_c05():
    snap = _run_review("L-C-005", _clauses_for("C-05"), _std_clauses(*ALL_RULEBOOK))
    try:
        payment = [f for f in snap if f["area"] == "payment"]
        assert len(payment) == 1                                   # 7.
        assert payment[0]["sharia"] is True
        lowered = payment[0]["statement"].lower()
        assert "interest" in lowered and "penalty" in lowered
        assert "scholar review" in lowered                         # flagged, not ruled
        assert "no ruling" in lowered
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


def test_no_sharia_flag_when_no_interest_charge_c01():
    # C-01 clause 3 explicitly says NO interest applies — negation-aware.
    snap = _run_review("L-C-001", _clauses_for("C-01"), _std_clauses(*ALL_RULEBOOK))
    try:
        assert all(not f["sharia"] for f in snap)
        assert not any(f["area"] == "payment" for f in snap)
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


# ---------------------------------------------------------------------------
# Grounding & citations
# ---------------------------------------------------------------------------

def test_every_grounded_finding_cites_its_contract_clause():
    snap = _run_review(
        "L-C-004", _clauses_for("C-04"), _std_clauses(*ALL_RULEBOOK), commit=True
    )
    ids = [f["id"] for f in snap]
    try:
        with SessionLocal() as verify:
            for f in snap:
                if not f["grounded"]:
                    continue
                citations = verify.scalars(
                    select(Citation).where(Citation.finding_id == f["id"])
                ).all()
                contract_citations = [
                    c for c in citations if c.source_type == "contract_clause"
                ]
                assert contract_citations, f"finding {f['id']} lacks a contract-clause citation"
                for c in contract_citations:                       # 11./15.
                    assert verify.get(ContractClause, c.contract_clause_id) is not None
    finally:
        _cleanup_finding_ids(ids)


def test_rulebook_assessment_cites_standard_clauses():
    snap = _run_review(
        "L-C-002", _clauses_for("C-02"), _std_clauses(*ALL_RULEBOOK), commit=True
    )
    ids = [f["id"] for f in snap]
    try:
        with SessionLocal() as verify:
            term = next(f for f in snap if f["area"] == "term_renewal")
            citations = verify.scalars(
                select(Citation).where(Citation.finding_id == term["id"])
            ).all()
            numbers = {
                verify.get(ReviewStandardClause, c.standard_clause_id).clause_number
                for c in citations
                if c.source_type == "standard_clause"
            }
            assert "1.1" in numbers                                # 12.
            assert "3.2" in numbers                                # medium-risk rule cited
    finally:
        _cleanup_finding_ids(ids)


def test_arabic_review_preserves_arabic_source_and_citation():
    source = load_data.parse_contract(
        load_data.DATA_DIR / "contracts" / "C-09_Hijaz_Supply_AR.txt"
    )
    expected_term_text = next(
        cl["text"] for cl in source["clauses"] if cl["clause_label"] == "1"
    )

    snap = _run_review(
        "L-C-009", _clauses_for("C-09"), _std_clauses(*ALL_RULEBOOK), commit=True
    )
    ids = [f["id"] for f in snap]
    try:
        term = next(f for f in snap if f["area"] == "term_renewal")
        assert term["tricky"] == "auto_renewal"
        assert "60 days" in term["statement"]                      # Arabic 60-day window parsed

        with SessionLocal() as verify:
            citations = verify.scalars(
                select(Citation).where(Citation.finding_id == term["id"])
            ).all()
            contract_cit = next(
                c for c in citations if c.source_type == "contract_clause"
            )
            cited_clause = verify.get(ContractClause, contract_cit.contract_clause_id)
            assert cited_clause.contract_id == "C-09"              # 13.
            assert cited_clause.text == expected_term_text         # Arabic unchanged
            assert ARABIC_RE.search(cited_clause.text)

        payment = [f for f in snap if f["sharia"]]
        assert payment, "Arabic penalty clause must be flagged"
    finally:
        _cleanup_finding_ids(ids)


# ---------------------------------------------------------------------------
# Risk framework derivation (rulebook 3.1–3.3 — never hard-coded)
# ---------------------------------------------------------------------------

def test_risk_framework_derived_from_seeded_rulebook():
    fw = derive_risk_framework(_std_clauses("3.1", "3.2", "3.3"))   # 10.
    assert isinstance(fw, RiskFramework)
    assert fw.labels == {"high": "high", "medium": "medium", "low": "low"}
    assert fw.high_notice_window_days == 30   # parsed from 3.1 text
    assert fw.long_payment_days == 60         # parsed from 3.2 text


def test_ratings_omitted_when_rulebook_section_not_supplied():
    snap = _run_review(
        "L-C-001", _clauses_for("C-01"), _std_clauses("1.1")
    )  # no section 3 supplied
    try:
        term = next(f for f in snap if f["area"] == "term_renewal")
        assert term["risk"] is None   # rulebook 3.4: never rate without the rule
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


# ---------------------------------------------------------------------------
# Security boundary & determinism
# ---------------------------------------------------------------------------

def test_review_queries_no_authorization_or_document_tables():
    clauses = _clauses_for("C-04")   # fetched OUTSIDE the spy by the test
    std = _std_clauses(*ALL_RULEBOOK)
    try:
        with sql_spy() as statements:
            snap = _run_review("L-C-004", clauses, std)

        forbidden = ("matter_assignment", "access_decision", "data_room_file")
        touched = [s for s in statements if any(t in s for t in forbidden)]
        assert not touched, f"review queried forbidden tables: {touched}"       # 16./17.
        doc_selects = [
            s
            for s in statements
            if re.search(r"from\s+(contract|contract_clause|review_standard_clause)\b", s)
        ]
        assert not doc_selects, f"review independently retrieved documents: {doc_selects}"
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


def test_only_supplied_clauses_are_reviewed():
    # Supply term + liability + governing-law + signature clauses but EXCLUDE
    # C-01's payment clause (which exists in the database): exactly three
    # findings, and no payment finding may appear.
    supplied = [
        c for c in _clauses_for("C-01") if c.clause_label in {"1", "7", "9", "12"}
    ]
    snap = _run_review("L-C-001", supplied, _std_clauses(*ALL_RULEBOOK))
    try:
        areas = sorted(f["area"] for f in snap)                    # 18.
        assert areas == ["governing_law", "liability", "term_renewal"]
        assert not any(f["area"] == "payment" for f in snap)
    finally:
        _cleanup_finding_ids([f["id"] for f in snap])


def test_review_is_deterministic_across_runs():
    clauses = _clauses_for("C-03")
    std = _std_clauses(*ALL_RULEBOOK)
    snapshots = []
    all_ids: list[list] = []
    try:
        for _ in range(2):
            snap = _run_review("L-C-003", clauses, std)
            snapshots.append(
                sorted((f["area"], f["tricky"], f["risk"], f["grounded"]) for f in snap)
            )
            all_ids.append([f["id"] for f in snap])
        assert snapshots[0] == snapshots[1]
    finally:
        for ids in all_ids:
            _cleanup_finding_ids(ids)


def test_unknown_request_rejected():
    with SessionLocal() as session:
        with pytest.raises(ValueError):
            review_contract(
                session,
                request_id="TST-NO-SUCH-REQUEST",
                contract_clauses=_clauses_for("C-01"),
                standard_clauses=_std_clauses(*ALL_RULEBOOK),
            )
        session.rollback()
    assert _count(Finding) == 0


def test_full_answer_key_alignment_c01_to_c06():
    """End-to-end alignment with answer_key ground truth for the tricky set."""
    expectations = {
        # C-01/C-02 also carry capped-liability clauses (answer_key cites
        # Clause 7 for both), so capped_liability belongs in their sets.
        "L-C-001": ("C-01", {"fixed_expiry", "capped_liability"}, {"liability": "low"}, False),
        "L-C-002": ("C-02", {"auto_renewal", "capped_liability"}, {}, False),
        # C-03 clause 1 is also a genuine fixed term expiring 31 Dec 2028.
        "L-C-003": (
            "C-03",
            {"fixed_expiry", "capped_with_uncapped_carveout", "uncapped_liability"},
            {},
            False,
        ),
        # C-04 clause 1 is a fixed 6-month term with no renewal.
        "L-C-004": ("C-04", {"fixed_expiry", "capped_liability"}, {"liability": "low"}, False),
        "L-C-005": ("C-05", {"uncapped_liability"}, {}, True),
        "L-C-006": ("C-06", set(), {}, False),
    }
    all_ids: list[list] = []
    try:
        for request_id, (contract_id, tricky_set, risk_by_area, expect_sharia) in expectations.items():
            snap = _run_review(
                request_id, _clauses_for(contract_id), _std_clauses(*ALL_RULEBOOK), commit=True
            )
            all_ids.append([f["id"] for f in snap])

            produced_tricky = {f["tricky"] for f in snap} - {None}
            assert produced_tricky == tricky_set, (request_id, produced_tricky)
            for area, risk in risk_by_area.items():
                match = [f for f in snap if f["area"] == area]
                assert match and match[0]["risk"] == risk, request_id
            assert any(f["sharia"] for f in snap) is expect_sharia, request_id
    finally:
        for ids in all_ids:
            _cleanup_finding_ids(ids)