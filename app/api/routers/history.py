"""Request history endpoints (FR-033)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_session
from app.api.schemas import AuditEventResponse, RequestHistoryResponse
from app.models import AuditEvent, Request

router = APIRouter(prefix="/requests", tags=["history"], dependencies=[Depends(get_current_user)])


@router.get("/{request_id}/history", response_model=RequestHistoryResponse)
def get_request_history(
    request_id: str,
    session: Session = Depends(get_session),
) -> RequestHistoryResponse:
    """Return the full audit lifecycle of a request."""
    if session.get(Request, request_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")

    events = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.request_id == request_id)
            .order_by(AuditEvent.occurred_at)
        ).all()
    )
    return RequestHistoryResponse(
        request_id=request_id,
        events=[AuditEventResponse.model_validate(e) for e in events],
    )


# ---------------------------------------------------------------------------
# Global audit feed (read-only view over the same append-only AuditEvent rows)
# ---------------------------------------------------------------------------

audit_router = APIRouter(prefix="/audit", tags=["history"], dependencies=[Depends(get_current_user)])


@audit_router.get("", response_model=list[AuditEventResponse])
def list_audit_events(
    event_type: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[AuditEventResponse]:
    """List audit events across all matters, newest first.

    Same read-only projection as the request-scoped history endpoint, but not
    filtered by ``request_id`` unless the caller asks for one matter — so
    events with ``request_id IS NULL`` (e.g. obligation-sweep escalations) are
    included. Optional equality filters: ``event_type``, ``request_id``,
    ``actor_id``.
    """
    stmt = select(AuditEvent)
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if request_id is not None:
        stmt = stmt.where(AuditEvent.request_id == request_id)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    stmt = stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.audit_event_id.desc())
    stmt = stmt.limit(limit).offset(offset)
    events = list(session.scalars(stmt).all())
    return [AuditEventResponse.model_validate(e) for e in events]
