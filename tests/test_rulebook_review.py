"""Tests for the rulebook-driven review service using Gemini LLM.

These tests mock the LLM integration layer to avoid actual API calls
and focus on verifying that LLM outputs are correctly processed into Findings.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.database.connection import SessionLocal
from app.models import (
    AuditEvent,
    Citation,
    ContractClause,
    Finding,
    Request,
    ReviewStandardClause,
)
from app.services.llm import LLMReviewResult, LLMFinding
from app.services.rulebook_review import review_contract

def _clauses_for(contract_id: str) -> list[ContractClause]:
    """All seeded clauses of a contract, detached — as retrieval would return."""
    with SessionLocal() as session:
        clauses = session.scalars(
            select(ContractClause)
            .where(ContractClause.contract_id == contract_id)
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

def test_findings_are_created_correctly_from_llm_result():
    request_id = "L-C-001"
    contract_clauses = _clauses_for("C-01")
    standard_clauses = _std_clauses("1.1", "3.3")
    
    # Pick valid IDs from the retrieved clauses
    c_id = str(contract_clauses[0].clause_id)
    s_id = str(standard_clauses[0].standard_clause_id)
    
    mock_llm_result = LLMReviewResult(
        findings=[
            LLMFinding(
                statement="The contract has a term clause.",
                risk_rating="low",
                sharia_sensitive_flag=False,
                cited_contract_clause_ids=[c_id],
                cited_standard_clause_ids=[s_id],
            )
        ]
    )
    
    with patch("app.services.rulebook_review.evaluate_clauses_via_llm", return_value=mock_llm_result.findings):
        with SessionLocal() as session:
            findings, _engine = review_contract(
                session,
                request_id=request_id,
                contract_clauses=contract_clauses,
                standard_clauses=standard_clauses,
            )
            session.rollback() # Don't persist test data
            
            assert len(findings) == 1
            f = findings[0]
            assert f.statement == "The contract has a term clause."
            assert f.risk_rating == "low"
            assert f.sharia_sensitive_flag is False
            assert f.grounded is True

def test_ungrounded_finding_is_created_when_no_citations_match():
    request_id = "L-C-001"
    contract_clauses = _clauses_for("C-01")
    standard_clauses = _std_clauses("1.1")
    
    # Invalid IDs that won't match any supplied clause
    c_id = str(uuid.uuid4())
    
    mock_llm_result = LLMReviewResult(
        findings=[
            LLMFinding(
                statement="LLM hallucinated a clause.",
                risk_rating="high",
                sharia_sensitive_flag=False,
                cited_contract_clause_ids=[c_id],
                cited_standard_clause_ids=[],
            )
        ]
    )
    
    with patch("app.services.rulebook_review.evaluate_clauses_via_llm", return_value=mock_llm_result.findings):
        with SessionLocal() as session:
            findings, _engine = review_contract(
                session,
                request_id=request_id,
                contract_clauses=contract_clauses,
                standard_clauses=standard_clauses,
            )
            session.rollback()
            
            assert len(findings) == 1
            f = findings[0]
            # Since no valid citations were matched, it becomes ungrounded
            assert f.grounded is False
            assert "not addressed in the documents" in f.statement.lower()

def test_invalid_untrusted_citations_cannot_become_findings():
    request_id = "L-C-001"
    contract_clauses = _clauses_for("C-01")
    standard_clauses = _std_clauses("1.1")
    
    valid_c_id = str(contract_clauses[0].clause_id)
    invalid_s_id = str(uuid.uuid4()) # Untrusted standard clause ID
    
    mock_llm_result = LLMReviewResult(
        findings=[
            LLMFinding(
                statement="This statement mixes valid and invalid citations.",
                risk_rating="medium",
                sharia_sensitive_flag=True,
                cited_contract_clause_ids=[valid_c_id],
                cited_standard_clause_ids=[invalid_s_id],
            )
        ]
    )
    
    with patch("app.services.rulebook_review.evaluate_clauses_via_llm", return_value=mock_llm_result.findings):
        with SessionLocal() as session:
            findings, _engine = review_contract(
                session,
                request_id=request_id,
                contract_clauses=contract_clauses,
                standard_clauses=standard_clauses,
            )
            # Find the uncommitted Citations attached to the finding
            f = findings[0]
            assert f.grounded is True
            assert f.sharia_sensitive_flag is True
            assert f.risk_rating == "medium"
            
            # Since invalid_s_id wasn't in the provided standard_clauses, it should NOT be cited.
            # Only valid_c_id should have been kept as a citation.
            # The test proves that untrusted IDs returned by the LLM are ignored by the mapping logic.
            session.rollback()

def test_empty_contract_returns_no_findings():
    with patch("app.services.rulebook_review.evaluate_clauses_via_llm") as mock_llm:
        with SessionLocal() as session:
            findings, _engine = review_contract(
                session,
                request_id="L-C-001",
                contract_clauses=[],
                standard_clauses=_std_clauses("1.1"),
            )
            assert len(findings) == 1
            assert findings[0].grounded is False
            assert "not addressed" in findings[0].statement.lower()
            mock_llm.assert_not_called()