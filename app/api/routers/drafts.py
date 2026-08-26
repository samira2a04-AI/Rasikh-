"""Draft endpoints (FR-028, APR-001–APR-003)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_session, transactional
from app.api.schemas import DraftCreate, DraftResponse
from app.models import Draft, User
from app.services import drafting, workflow

router = APIRouter(prefix="/requests", tags=["drafts"], dependencies=[Depends(get_current_user)])


@router.post("/{request_id}/drafts", response_model=DraftResponse, status_code=201)
def create_draft(
    request_id: str,
    body: DraftCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DraftResponse:
    """Create a new draft version for a request."""
    with transactional(session):
        draft = workflow.prepare_draft(
            session,
            request_id=request_id,
            content=body.content,
            created_at=body.created_at,
            created_by=current_user.member_id,
        )
        session.commit()
    return DraftResponse.model_validate(draft)


@router.get("/{request_id}/drafts", response_model=list[DraftResponse])
def list_drafts(
    request_id: str,
    session: Session = Depends(get_session),
) -> list[DraftResponse]:
    """List all draft versions for a request."""
    drafts = list(
        session.scalars(
            select(Draft)
            .where(Draft.request_id == request_id)
            .order_by(Draft.version)
        ).all()
    )
    return [DraftResponse.model_validate(d) for d in drafts]


@router.get("/{request_id}/drafts/{draft_id}", response_model=DraftResponse)
def get_draft(
    request_id: str,
    draft_id: str,
    session: Session = Depends(get_session),
) -> DraftResponse:
    """Return a single draft by id."""
    draft = session.get(Draft, draft_id)
    if draft is None or draft.request_id != request_id:
        raise HTTPException(
            status_code=404,
            detail=f"unknown draft_id {draft_id!r} for request {request_id!r}",
        )
    return DraftResponse.model_validate(draft)
