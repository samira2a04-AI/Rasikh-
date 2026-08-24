"""Grounded review persistence boundary (FR-011, FR-019, FR-020, GRD-001–GRD-007).

This module is NOT the AI layer. It is the deterministic persistence gate a
later review engine MUST use to record Findings and Citations, establishing
the grounding guarantees described in docs/data-schema.md §7:

- ``grounded=True``  -> the Finding carries >= 1 Citation, and every Citation
  points at a ContractClause / ReviewStandardClause instance that the caller
  explicitly supplied (i.e. material the authorised retrieval layer actually
  returned). Existence of the referenced row is enforced by the database
  foreign keys (GRD-004) when the caller's transaction flushes.
- ``grounded=False`` -> the Finding carries ZERO Citations and its statement
  must contain the rulebook 0.1 wording — "not addressed in the documents"
  (rulebook clause 0.1: "this is not addressed in the documents provided").

SECURITY BOUNDARY: this service never queries contracts, data-room files, or
standard clauses itself, never calls :mod:`app.services.access_control`, and
never derives anything from ``Request.raw_content``. It operates exclusively
on what the caller passes in: the request identifier and already-retrieved
clause instances. Citations can ONLY be created from supplied ORM instances —
there is no code path that accepts a bare clause id, so IDs cannot be
fabricated through this API.

Risk rating is persisted exactly as supplied and deliberately NOT validated
against a hard-coded taxonomy: docs/data-schema.md §9 keeps the allowed values
in the rulebook, read at runtime by the later risk-analysis component.

Transaction convention: no ``commit()`` here; the caller owns the transaction.
A single ``flush()`` at the end makes FK violations surface immediately, and
because Finding + Citations + AuditEvent are added together, any failure rolls
back atomically — no partial Finding can survive.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Citation,
    ContractClause,
    Finding,
    Request,
    ReviewStandardClause,
)

EVENT_FINDING_PRODUCED = "finding_produced"

# Checklist areas defined by docs/data-schema.md §3 (finding.checklist_area /
# contract_clause.checklist_area). No other values exist in the specification.
CHECKLIST_AREAS = frozenset(
    {"term_renewal", "liability", "payment", "termination", "governing_law", "gap", "other"}
)

# Tricky-case vocabulary defined by docs/data-schema.md §3
# (finding.tricky_case_type). These mirror the documented pairs (FR-021).
TRICKY_CASE_TYPES = frozenset(
    {
        "fixed_expiry",
        "auto_renewal",
        "capped_liability",
        "uncapped_liability",
        "capped_with_uncapped_carveout",
        "none",
    }
)

# Canonical grounding language from rulebook clause 0.1 / architecture §6.
NOT_IN_DOCUMENTS_PHRASE = "not addressed in the documents"


class ReviewPersistenceError(ValueError):
    """Raised when a Finding/Citation cannot be created as requested."""


def _validate_optional_vocabulary(
    *,
    checklist_area: str | None,
    tricky_case_type: str | None,
) -> None:
    if checklist_area is not None and checklist_area not in CHECKLIST_AREAS:
        raise ReviewPersistenceError(
            f"unsupported checklist_area {checklist_area!r}; expected one of "
            f"{sorted(CHECKLIST_AREAS)}"
        )
    if tricky_case_type is not None and tricky_case_type not in TRICKY_CASE_TYPES:
        raise ReviewPersistenceError(
            f"unsupported tricky_case_type {tricky_case_type!r}; expected one of "
            f"{sorted(TRICKY_CASE_TYPES)}"
        )


def _require_request(session: Session, request_id: str) -> None:
    if session.get(Request, request_id) is None:
        raise ReviewPersistenceError(f"unknown request_id {request_id!r}")


def _source_ref(source: ContractClause | ReviewStandardClause) -> tuple[str, object]:
    """Map a supplied retrieved-clause instance to its citation reference."""
    if isinstance(source, ContractClause):
        return "contract_clause", source.clause_id
    if isinstance(source, ReviewStandardClause):
        return "standard_clause", source.standard_clause_id
    raise ReviewPersistenceError(
        "citations must be retrieved ContractClause or ReviewStandardClause "
        "instances supplied by the caller — bare identifiers are not accepted"
    )


def _add_citations(
    session: Session,
    *,
    finding_id: object,
    sources: list[ContractClause | ReviewStandardClause],
) -> int:
    for source in sources:
        source_type, source_id = _source_ref(source)
        session.add(
            Citation(
                finding_id=finding_id,
                source_type=source_type,
                contract_clause_id=source_id if source_type == "contract_clause" else None,
                standard_clause_id=source_id if source_type == "standard_clause" else None,
            )
        )
    return len(sources)


def _add_finding_produced_event(
    session: Session,
    *,
    request_id: str,
    finding_id: object,
    grounded: bool,
    citation_count: int,
) -> None:
    session.add(
        AuditEvent(
            request_id=request_id,
            event_type=EVENT_FINDING_PRODUCED,
            actor_id=None,  # produced by the review engine (system), not a member
            detail_reference=f"finding:{finding_id}",
            detail_json={"grounded": grounded, "citation_count": citation_count},
        )
    )


def create_grounded_finding(
    session: Session,
    *,
    request_id: str,
    statement: str,
    citations: list[ContractClause | ReviewStandardClause],
    checklist_area: str | None = None,
    risk_rating: str | None = None,
    sharia_sensitive_flag: bool = False,
    tricky_case_type: str | None = None,
) -> Finding:
    """Create a grounded Finding with >= 1 Citation to supplied source clauses.

    ``citations`` must be non-empty and may only contain ContractClause /
    ReviewStandardClause instances that the caller received from the
    authorised retrieval layer. ``risk_rating`` is persisted verbatim (the
    taxonomy lives in the rulebook, applied later by Risk Analysis).
    """
    _validate_optional_vocabulary(
        checklist_area=checklist_area, tricky_case_type=tricky_case_type
    )
    _require_request(session, request_id)

    if not citations:
        raise ReviewPersistenceError(
            "a grounded finding requires at least one citation to a supplied "
            "ContractClause or ReviewStandardClause"
        )

    finding = Finding(
        request_id=request_id,
        checklist_area=checklist_area,
        statement=statement,
        grounded=True,
        risk_rating=risk_rating,
        sharia_sensitive_flag=sharia_sensitive_flag,
        tricky_case_type=tricky_case_type,
    )
    session.add(finding)
    session.flush()  # assign the PK so citations can reference it

    citation_count = _add_citations(session, finding_id=finding.finding_id, sources=list(citations))
    _add_finding_produced_event(
        session,
        request_id=request_id,
        finding_id=finding.finding_id,
        grounded=True,
        citation_count=citation_count,
    )
    session.flush()  # surface FK violations (GRD-004) immediately
    return finding


def create_ungrounded_finding(
    session: Session,
    *,
    request_id: str,
    statement: str,
    checklist_area: str | None = None,
) -> Finding:
    """Create an explicit "not in the documents" Finding with ZERO citations.

    The statement must contain the rulebook 0.1 wording so the honest
    negative outcome is unmistakable (FR-020, GRD-005).
    """
    _validate_optional_vocabulary(checklist_area=checklist_area, tricky_case_type=None)
    _require_request(session, request_id)

    if NOT_IN_DOCUMENTS_PHRASE not in statement.lower():
        raise ReviewPersistenceError(
            "an ungrounded finding must state plainly that the information is "
            f"{NOT_IN_DOCUMENTS_PHRASE!r} (rulebook clause 0.1)"
        )

    finding = Finding(
        request_id=request_id,
        checklist_area=checklist_area,
        statement=statement,
        grounded=False,
        risk_rating=None,
        sharia_sensitive_flag=False,
        tricky_case_type=None,
    )
    session.add(finding)
    session.flush()  # assign the PK for the audit reference

    _add_finding_produced_event(
        session,
        request_id=request_id,
        finding_id=finding.finding_id,
        grounded=False,
        citation_count=0,
    )
    session.flush()
    return finding