"""Request intake endpoints (FR-001, FR-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import CurrentUser, get_current_user
from app.api.dependencies import get_session, transactional
from app.api.schemas import RequestResponse, RequestSubmit
from app.models import AuditEvent, Request
from app.services import request_intake, workflow

router = APIRouter(prefix="/requests", tags=["requests"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[RequestResponse])
def list_requests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[RequestResponse]:
    """List requests, newest first (simple limit/offset pagination)."""
    rows = session.scalars(
        select(Request)
        .order_by(Request.created_at.desc(), Request.request_id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [RequestResponse.model_validate(row) for row in rows]


@router.post("", response_model=RequestResponse, status_code=201)
def submit_request(
    body: RequestSubmit,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> RequestResponse:
    """Submit a new request and classify it.

    When ``body.requester_id`` is omitted, it is derived from the authenticated
    user's mapped team member (``current_user.member_id``). A mapped account
    always resolves; an unmapped account cannot author a request. An explicitly
    supplied ``requester_id`` is still honoured and validated at intake.
    """
    requester_id = body.requester_id
    if requester_id is None:
        requester_id = current_user.member_id
        if requester_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "no requester_id supplied and the authenticated account is "
                    "not mapped to a firm team member"
                ),
            )

    with transactional(session):
        if body.request_type is not None:
            request = workflow.intake_and_classify(
                session,
                request_id=body.request_id,
                requester_id=requester_id,
                raw_content=body.raw_content,
                org_id=body.org_id,
                request_type=body.request_type,
                created_at=body.created_at,
            )
        else:
            request = request_intake.submit_request(
                session,
                request_id=body.request_id,
                requester_id=requester_id,
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
