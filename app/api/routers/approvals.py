import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_dependencies import CurrentUser, get_current_user
from app.api.dependencies import get_session, transactional
from app.api.schemas import ApprovalRequest, ApprovalResponse
from app.models import Draft, Request, User
from app.services import access_control, workflow

router = APIRouter(prefix="/drafts", tags=["approvals"], dependencies=[Depends(get_current_user)])


def _ensure_draft_matter_access(session: Session, draft_id: str, current_user: User) -> Draft:
    try:
        val_id = uuid.UUID(draft_id) if isinstance(draft_id, str) else draft_id
    except (ValueError, AttributeError):
        val_id = draft_id
    draft = session.get(Draft, val_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"unknown draft_id {draft_id!r}")
    req = session.get(Request, draft.request_id)
    if req and req.org_id and current_user.member_id:
        access_res = access_control.check_access(
            session, member_id=current_user.member_id, org_id=req.org_id
        )
        if not access_res.authorized:
            raise HTTPException(status_code=403, detail="Not authorized to decide drafts for this matter")
    return draft


@router.post("/{draft_id}/approve", response_model=ApprovalResponse)
def approve_draft(
    draft_id: str,
    body: ApprovalRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> ApprovalResponse:
    """Record a lawyer's approval of the current draft version."""
    _ensure_draft_matter_access(session, draft_id, current_user)
    reviewer_id = body.reviewer_id or current_user.member_id or ""
    with transactional(session):
        try:
            decision = workflow.approve_current_draft(
                session,
                draft_id=draft_id,
                reviewer_id=reviewer_id,
            )
            session.commit()
            return ApprovalResponse.model_validate(decision)
        except Exception as exc:
            msg = str(exc)
            if hasattr(exc, "__cause__") and exc.__cause__:
                msg = str(exc.__cause__)
            if "approval authority" in msg or "cannot approve" in msg or "separation of duties" in msg:
                raise HTTPException(status_code=403, detail=msg)
            elif "stale" in msg or "already" in msg or "terminal" in msg:
                raise HTTPException(status_code=409, detail=msg)
            elif "unknown" in msg:
                raise HTTPException(status_code=404, detail=msg)
            raise HTTPException(status_code=400, detail=msg)


@router.post("/{draft_id}/reject", response_model=ApprovalResponse)
def reject_draft(
    draft_id: str,
    body: ApprovalRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> ApprovalResponse:
    """Record a lawyer's rejection of the current draft version."""
    _ensure_draft_matter_access(session, draft_id, current_user)
    reviewer_id = body.reviewer_id or current_user.member_id or ""
    with transactional(session):
        try:
            decision = workflow.reject_current_draft(
                session,
                draft_id=draft_id,
                reviewer_id=reviewer_id,
            )
            session.commit()
            return ApprovalResponse.model_validate(decision)
        except Exception as exc:
            msg = str(exc)
            if hasattr(exc, "__cause__") and exc.__cause__:
                msg = str(exc.__cause__)
            if "approval authority" in msg or "cannot approve" in msg or "separation of duties" in msg:
                raise HTTPException(status_code=403, detail=msg)
            elif "stale" in msg or "already" in msg or "terminal" in msg:
                raise HTTPException(status_code=409, detail=msg)
            elif "unknown" in msg:
                raise HTTPException(status_code=404, detail=msg)
            raise HTTPException(status_code=400, detail=msg)
