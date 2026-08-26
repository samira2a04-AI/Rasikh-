"""Secure document-retrieval service.

Security boundary (SEC-002, Rule 1, docs/system-architecture.md §5–§6):

Every retrieval function requires ``(request_id, member_id, org_id)`` and
refuses to touch any document unless a recorded ``AccessDecision`` with
``outcome = 'authorized'`` exists for EXACTLY that triple. The recorded
decision — not a re-run of the access rule — is the gate here, so retrieval
can never disagree with what access control already decided.

Organisation isolation (SEC-007): organisation-scoped queries always filter
by ``org_id``; contract clauses are reachable only through a parent contract
belonging to the authorised organisation.

Privilege (SEC-004): ``DataRoomFile.privileged`` is preserved verbatim on
every returned row. No additional privilege policy is implemented here — the
architecture keeps the exact privileged-access rule as an application-level
concern downstream of retrieval.

Audit (FR-033, SEC-006, docs/data-schema.md §5): a successful retrieval
appends one append-only ``AuditEvent`` with ``event_type =
'document_retrieved'`` (an event type named by the existing specification),
pointing at the retrieved rows via ``detail_reference``. Denied attempts
raise :class:`DocumentAccessDenied` and write NOTHING: the authoritative
record of a denial is the ``AccessDecision`` row with ``outcome =
'unauthorized'`` created by the access-control service — this module never
fabricates a ``document_retrieved`` event for a failed retrieval.

No LLM/AI component, embedding store, or network call participates in this
module; it is plain SQLAlchemy against the authorised database session.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccessDecision,
    AuditEvent,
    Contract,
    ContractClause,
    DataRoomFile,
    ReviewStandardClause,
)

EVENT_DOCUMENT_RETRIEVED = "document_retrieved"


class DocumentAccessDenied(PermissionError):
    """Raised when no authorised AccessDecision exists for the given
    ``(request_id, member_id, org_id)`` triple, or when the requested
    document does not belong to the authorised organisation.

    No document data is returned or exposed when this is raised.
    """


def require_authorized_access(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
) -> None:
    """Verify a recorded authorised AccessDecision for the exact triple.

    Queries the ``access_decision`` table only. Raises
    :class:`DocumentAccessDenied` when no matching ``outcome = 'authorized'``
    row exists. This is the single shared gate for every retrieval function.
    """
    authorized_decision_exists = (
        session.execute(
            select(AccessDecision.access_decision_id)
            .where(
                AccessDecision.request_id == request_id,
                AccessDecision.member_id == member_id,
                AccessDecision.org_id == org_id,
                AccessDecision.outcome == "authorized",
            )
            .limit(1)
        ).first()
        is not None
    )
    if not authorized_decision_exists:
        raise DocumentAccessDenied(
            "no authorized AccessDecision for "
            f"(request_id={request_id!r}, member_id={member_id!r}, org_id={org_id!r})"
        )


def _record_document_retrieved(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    detail_reference: str,
    detail: dict,
) -> None:
    """Append the append-only ``document_retrieved`` audit event.

    Added to the session but NOT committed — the caller owns the transaction,
    matching the access-control service pattern.
    """
    session.add(
        AuditEvent(
            request_id=request_id,
            event_type=EVENT_DOCUMENT_RETRIEVED,
            actor_id=member_id,
            detail_reference=detail_reference,
            detail_json=detail,
        )
    )


def retrieve_contracts(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
) -> list[Contract]:
    """Return the authorised organisation's contracts (matter isolation)."""
    require_authorized_access(
        session, request_id=request_id, member_id=member_id, org_id=org_id
    )

    contracts = list(
        session.scalars(select(Contract).where(Contract.org_id == org_id)).all()
    )

    _record_document_retrieved(
        session,
        request_id=request_id,
        member_id=member_id,
        detail_reference="contract:" + ",".join(c.contract_id for c in contracts),
        detail={"org_id": org_id, "count": len(contracts)},
    )
    return contracts


def retrieve_contract_clauses(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
    contract_id: str,
) -> list[ContractClause]:
    """Return a contract's clauses — only if the contract belongs to the
    authorised organisation.

    A contract that does not exist or belongs to a different organisation is
    indistinguishable here: both raise :class:`DocumentAccessDenied`, leaking
    nothing. Arabic clause text is returned unchanged.
    """
    require_authorized_access(
        session, request_id=request_id, member_id=member_id, org_id=org_id
    )

    contract = session.execute(
        select(Contract).where(
            Contract.contract_id == contract_id,
            Contract.org_id == org_id,
        )
    ).scalar_one_or_none()
    if contract is None:
        raise DocumentAccessDenied(
            f"contract {contract_id!r} does not belong to authorised "
            f"organisation {org_id!r}"
        )

    clauses = list(
        session.scalars(
            select(ContractClause)
            .where(ContractClause.contract_id == contract_id)
            .order_by(ContractClause.clause_label)
        ).all()
    )

    _record_document_retrieved(
        session,
        request_id=request_id,
        member_id=member_id,
        detail_reference=f"contract_clause:{contract_id}",
        detail={"org_id": org_id, "clause_count": len(clauses)},
    )
    return clauses


def retrieve_data_room_files(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
) -> list[DataRoomFile]:
    """Return the organisation's data-room files with ``privileged`` intact.

    Privileged files (e.g. DR-04) pass through the SAME authorisation gate as
    everything else; the flag is preserved for the caller's independent
    privilege handling (SEC-004).
    """
    require_authorized_access(
        session, request_id=request_id, member_id=member_id, org_id=org_id
    )

    files = list(
        session.scalars(
            select(DataRoomFile).where(DataRoomFile.org_id == org_id)
        ).all()
    )

    _record_document_retrieved(
        session,
        request_id=request_id,
        member_id=member_id,
        detail_reference="data_room_file:" + ",".join(f.file_id for f in files),
        detail={
            "org_id": org_id,
            "count": len(files),
            "privileged_included": any(f.privileged for f in files),
        },
    )
    return files


def retrieve_review_standard_clauses(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
    category: str | None = None,
    clause_number: str | None = None,
) -> list[ReviewStandardClause]:
    """Return firm review-standard clauses for an authorised request.

    The corpus is firm policy rather than organisation-confidential, but per
    docs/system-architecture.md §6 "the standard's *use* still requires that
    the calling request has already passed the matter access check" — so the
    same recorded-authorisation gate applies. Optional deterministic filters:
    ``category`` and/or ``clause_number``.
    """
    require_authorized_access(
        session, request_id=request_id, member_id=member_id, org_id=org_id
    )

    stmt = select(ReviewStandardClause).order_by(ReviewStandardClause.clause_number)
    if category is not None:
        stmt = stmt.where(ReviewStandardClause.category == category)
    if clause_number is not None:
        stmt = stmt.where(ReviewStandardClause.clause_number == clause_number)

    clauses = list(session.scalars(stmt).all())

    _record_document_retrieved(
        session,
        request_id=request_id,
        member_id=member_id,
        detail_reference=(
            "review_standard_clause:" + ",".join(c.clause_number for c in clauses)
        ),
        detail={"org_id": org_id, "count": len(clauses)},
    )
    return clauses

def retrieve_similar_contract_clauses(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
    contract_id: str,
    query_embedding: list[float],
    limit: int = 5,
) -> list[ContractClause]:
    """Return top-K contract clauses by cosine similarity (in-memory)."""
    clauses = retrieve_contract_clauses(
        session, request_id=request_id, member_id=member_id, org_id=org_id, contract_id=contract_id
    )
    
    if not clauses:
        return []
        
    query_vec = np.array(query_embedding)
    
    def cosine_sim(vec: list[float] | None) -> float:
        if not vec:
            return -1.0
        v = np.array(vec)
        norm_product = np.linalg.norm(query_vec) * np.linalg.norm(v)
        if norm_product == 0:
            return 0.0
        return float(np.dot(query_vec, v) / norm_product)
        
    clauses.sort(key=lambda c: cosine_sim(c.embedding), reverse=True)
    return clauses[:limit]

def retrieve_similar_review_standard_clauses(
    session: Session,
    *,
    request_id: str,
    member_id: str,
    org_id: str,
    query_embedding: list[float],
    limit: int = 5,
) -> list[ReviewStandardClause]:
    """Return top-K standard clauses by cosine similarity (in-memory)."""
    clauses = retrieve_review_standard_clauses(
        session, request_id=request_id, member_id=member_id, org_id=org_id
    )
    
    if not clauses:
        return []
        
    query_vec = np.array(query_embedding)
    
    def cosine_sim(vec: list[float] | None) -> float:
        if not vec:
            return -1.0
        v = np.array(vec)
        norm_product = np.linalg.norm(query_vec) * np.linalg.norm(v)
        if norm_product == 0:
            return 0.0
        return float(np.dot(query_vec, v) / norm_product)
        
    clauses.sort(key=lambda c: cosine_sim(c.embedding), reverse=True)
    return clauses[:limit]