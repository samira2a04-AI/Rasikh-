"""Rulebook-driven contract review using LLM and semantic search.

Replaces the previous regex mock with calls to the actual LLM evaluation layer.
"""

from __future__ import annotations
import uuid

from sqlalchemy.orm import Session

from app.models import ContractClause, Request, ReviewStandardClause
from app.services.review import (
    create_grounded_finding,
    create_ungrounded_finding,
)
import logging

from app.services.llm import LLMFinding, evaluate_clauses_via_llm

logger = logging.getLogger(__name__)

# Words too generic to be useful for deterministic keyword overlap.
_STOPWORDS = frozenset(
    """the a an of and or to in for with on by is are be been was were not
    shall should must may might will would can could this that these those
    any all each such from at as it its into upon under over between during
    before after within without per their his her our your they them he she
    we you i if then else when where which who whom whose what how no yes""".split()
)


_STANDARD_TOPIC_KEYWORDS = {
    "1.1": {"term", "renewal", "duration", "expiry", "expire", "commence", "effective", "auto-renew", "period"},
    "1.2": {"liability", "indemnify", "indemnity", "indemnification", "limitation", "cap", "loss", "damage", "carve-out"},
    "1.3": {"payment", "pay", "fee", "price", "invoice", "currency", "amount", "due", "schedule", "billing", "usd", "sar"},
    "1.4": {"terminate", "termination", "cancel", "cancellation", "breach", "notice", "convenience"},
    "1.5": {"governing", "law", "jurisdiction", "dispute", "court", "governed", "arbitration", "saudi", "english", "rules"},
    "1.6": {"confidential", "confidentiality", "disclosure", "nondisclosure", "privacy", "secret", "proprietary", "data"},
    "1.7": {"missing", "essential", "gap", "omitted"},
    "1.8": {"absent", "lacking", "omission"},
    "4.1": {"interest", "per annum", "usury", "riba", "finance charge"},
    "4.2": {"uncertainty", "speculation", "undefined", "gharar"},
    "4.3": {"penalty", "liquidated", "damages", "late fee", "fine", "sanction", "late payment"},
    "4.4": {"flag", "stop"},
}


def _content_words(text: str) -> set[str]:
    return {w.strip(".,;:()[]\"'").lower() for w in text.split() if len(w) > 2 and w.lower() not in _STOPWORDS}


def _deterministic_findings(
    contract_clauses: list[ContractClause],
    standard_clauses: list[ReviewStandardClause],
) -> list[LLMFinding]:
    """Deterministic clause-vs-standard review used when the LLM is
    unavailable (quota exhausted, network error, etc.).

    Each applicable contract-review standard clause is compared against the contract
    clauses via topic-focused keyword overlap; matches become grounded findings citing the real
    clause ORM ids, non-matches become explicit 'not addressed' findings.
    """
    applicable = [
        sc for sc in standard_clauses
        if sc.clause_number in ("1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "4.1", "4.2", "4.3")
    ]
    if not applicable:
        applicable = [
            sc for sc in standard_clauses
            if sc.clause_number.startswith("1.") or sc.clause_number.startswith("4.")
        ]

    findings: list[LLMFinding] = []
    for sc in applicable:
        is_sharia = sc.clause_number.startswith("4.") or sc.category == "sharia_sensitive"
        topic_words = _STANDARD_TOPIC_KEYWORDS.get(sc.clause_number, _content_words(sc.text))
        best_clause = None
        best_overlap = 0
        for cc in contract_clauses:
            overlap = len(topic_words & _content_words(cc.text))
            if overlap > best_overlap:
                best_overlap = overlap
                best_clause = cc
        if best_clause is not None and best_overlap >= 1:
            findings.append(
                LLMFinding(
                    statement=(
                        f"Standard clause {sc.clause_number} appears to be "
                        f"addressed by contract clause '{best_clause.clause_label}' "
                        f"(matched {best_overlap} key terms)."
                    ),
                    risk_rating="High risk" if (is_sharia or "unlimited" in best_clause.text.lower()) else "Low risk",
                    sharia_sensitive_flag=is_sharia,
                    cited_contract_clause_ids=[str(best_clause.clause_id)],
                    cited_standard_clause_ids=[str(sc.standard_clause_id)],
                )
            )
        else:
            findings.append(
                LLMFinding(
                    statement=(
                        f"Clause {sc.clause_number}: {sc.text} "
                        "(not addressed in the documents)"
                    ),
                    risk_rating=None,
                    sharia_sensitive_flag=is_sharia,
                    cited_contract_clause_ids=[],
                    cited_standard_clause_ids=[],
                )
            )
    return findings

def review_contract(
    session: Session,
    *,
    request_id: str,
    contract_clauses: list[ContractClause],
    standard_clauses: list[ReviewStandardClause],
    analysis_run_id=None,
) -> tuple[list[object], str]:
    """Review the provided contract clauses against the standard clauses.

    Returns (findings, engine) where ``engine`` reports which evaluator
    actually produced them: 'llm' or 'deterministic_fallback'. The fallback
    is recorded so fallback output is never presented as model output.
    """
    engine = "llm"

    if not contract_clauses:
        # If there are no contract clauses (document-less request or matter without linked contracts),
        # return a single grounded 'not in the documents' finding instead of falsely claiming
        # operational rulebook clauses are missing.
        engine = "deterministic_fallback"
        statement = "No source documents or contracts are linked to this organisation (not addressed in the documents)"
        finding = create_ungrounded_finding(
            session=session,
            request_id=request_id,
            statement=statement,
            analysis_run_id=analysis_run_id,
        )
        return [finding], engine

    # Filter standard_clauses to substantive contract-review standards
    # (Section 1: Contract Review Checklist & Section 4: Sharia-Sensitive Constructs).
    # System operating principles (Sections 0, 3, 5, 6: access control, privilege,
    # escalation, obligation calendar) are NOT contract clauses to evaluate as missing.
    applicable_standards = [
        sc for sc in standard_clauses
        if sc.clause_number.startswith("1.")
        or sc.clause_number.startswith("4.")
        or sc.category in ("review_checklist", "sharia_sensitive")
    ]
    if not applicable_standards:
        applicable_standards = list(standard_clauses)
        
    contract_text = "\n".join(
        f"[Clause ID: {c.clause_id}] (Label: {c.clause_label}) {c.text}"
        for c in contract_clauses
    )
    
    standard_text = "\n".join(
        f"[Standard Clause ID: {c.standard_clause_id}] (Number: {c.clause_number}) {c.text}"
        for c in applicable_standards
    )
    
    try:
        llm_findings = evaluate_clauses_via_llm(contract_text, standard_text)
    except Exception as exc:
        # LLM unavailable (quota exhausted / network / API error):
        # degrade gracefully to a deterministic clause-based review
        # instead of failing the whole request with a 500. The engine is
        # recorded so this output is distinguishable from Gemini output.
        logger.warning("LLM evaluation failed; using deterministic fallback: %s", exc)
        llm_findings = _deterministic_findings(contract_clauses, applicable_standards)
        engine = "deterministic_fallback"
    
    # Map back to ORM objects for grounded findings
    contract_clause_map = {str(c.clause_id): c for c in contract_clauses}
    standard_clause_map = {str(c.standard_clause_id): c for c in applicable_standards}
    
    created_findings = []
    
    for f in llm_findings:
        citations = []
        for cid in f.cited_contract_clause_ids:
            if cid in contract_clause_map:
                citations.append(contract_clause_map[cid])
        for sid in f.cited_standard_clause_ids:
            if sid in standard_clause_map:
                citations.append(standard_clause_map[sid])
                
        # Must have at least one citation to be grounded
        if citations and "not addressed in the documents" not in f.statement.lower():
            finding = create_grounded_finding(
                session=session,
                request_id=request_id,
                statement=f.statement,
                citations=citations,
                risk_rating=f.risk_rating,
                sharia_sensitive_flag=f.sharia_sensitive_flag,
                analysis_run_id=analysis_run_id,
            )
            created_findings.append(finding)
        else:
            statement = f.statement
            if "not addressed in the documents" not in statement.lower():
                statement += " (not addressed in the documents)"
            finding = create_ungrounded_finding(
                session=session,
                request_id=request_id,
                statement=statement,
                analysis_run_id=analysis_run_id,
            )
            created_findings.append(finding)

    return created_findings, engine