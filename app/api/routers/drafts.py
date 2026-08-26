import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import CurrentUser, get_current_user
from app.api.dependencies import get_session, transactional
from app.api.schemas import DraftCreate, DraftResponse
from app.models import Draft, Request, User
from app.services import access_control, drafting, workflow

router = APIRouter(prefix="/requests", tags=["drafts"], dependencies=[Depends(get_current_user)])


def _ensure_request_matter_access(session: Session, request_id: str, current_user: User) -> Request:
    req = session.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")
    if req.org_id and current_user and current_user.member_id:
        access_res = access_control.check_access(
            session, member_id=current_user.member_id, org_id=req.org_id
        )
        if not access_res.authorized:
            raise HTTPException(status_code=403, detail="Not authorized to access drafts for this matter")
    return req


@router.post("/{request_id}/drafts", response_model=DraftResponse, status_code=201)
def create_draft(
    request_id: str,
    body: DraftCreate,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> DraftResponse:
    """Create a new draft version for a request."""
    _ensure_request_matter_access(session, request_id, current_user)
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


@router.post(
    "/{request_id}/drafts/generate",
    response_model=DraftResponse,
    status_code=201,
)
def generate_ai_draft(
    request_id: str,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> DraftResponse:
    """Generate an AI draft from the request's completed analysis + reviewed findings."""
    _ensure_request_matter_access(session, request_id, current_user)
    with transactional(session):
        draft = workflow.generate_ai_draft(
            session,
            request_id=request_id,
            created_by=current_user.member_id,
        )
        session.commit()
    return DraftResponse.model_validate(draft)


@router.get("/{request_id}/drafts", response_model=list[DraftResponse])
def list_drafts(
    request_id: str,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> list[DraftResponse]:
    """List all draft versions for a request."""
    _ensure_request_matter_access(session, request_id, current_user)
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
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> DraftResponse:
    """Return a single draft by id."""
    _ensure_request_matter_access(session, request_id, current_user)
    try:
        val_id = uuid.UUID(draft_id) if isinstance(draft_id, str) else draft_id
    except (ValueError, AttributeError):
        val_id = draft_id
    draft = session.get(Draft, val_id)
    if draft is None or draft.request_id != request_id:
        raise HTTPException(
            status_code=404,
            detail=f"unknown draft_id {draft_id!r} for request {request_id!r}",
        )
    return DraftResponse.model_validate(draft)
