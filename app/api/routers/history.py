"""Request history endpoints (FR-033)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.api.schemas import AuditEventResponse, RequestHistoryResponse
from app.models import AuditEvent, Request

router = APIRouter(prefix="/requests", tags=["history"])


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
