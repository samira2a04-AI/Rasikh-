"""Request intake endpoints (FR-001, FR-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, transactional
from app.api.schemas import RequestResponse, RequestSubmit
from app.models import AuditEvent, Request
from app.services import request_intake, workflow

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=RequestResponse, status_code=201)
def submit_request(
    body: RequestSubmit,
    session: Session = Depends(get_session),
) -> RequestResponse:
    """Submit a new request and classify it."""
    with transactional(session):
        if body.request_type is not None:
            request = workflow.intake_and_classify(
                session,
                request_id=body.request_id,
                requester_id=body.requester_id,
                raw_content=body.raw_content,
                org_id=body.org_id,
                request_type=body.request_type,
                created_at=body.created_at,
            )
        else:
            request = request_intake.submit_request(
                session,
                request_id=body.request_id,
                requester_id=body.requester_id,
                raw_content=body.raw_content,
                org_id=body.org_id,
                created_at=body.created_at,
            )
        session.commit()
    return RequestResponse.model_validate(request)


@router.get("/{request_id}", response_model=RequestResponse)
def get_request(
    request_id: str,
    session: Session = Depends(get_session),
) -> RequestResponse:
    """Return a single request by id."""
    request = session.get(Request, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")
    return RequestResponse.model_validate(request)
