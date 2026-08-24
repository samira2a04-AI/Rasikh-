"""Approval endpoints (FR-029–FR-032, APR-001–APR-005)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, transactional
from app.api.schemas import ApprovalRequest, ApprovalResponse
from app.services import workflow

router = APIRouter(prefix="/drafts", tags=["approvals"])


@router.post("/{draft_id}/approve", response_model=ApprovalResponse)
def approve_draft(
    draft_id: str,
    body: ApprovalRequest,
    session: Session = Depends(get_session),
) -> ApprovalResponse:
    """Record a lawyer's approval of the current draft version."""
    with transactional(session):
        decision = workflow.approve_current_draft(
            session,
            draft_id=draft_id,
            reviewer_id=body.reviewer_id,
        )
        session.commit()
    return ApprovalResponse.model_validate(decision)


@router.post("/{draft_id}/reject", response_model=ApprovalResponse)
def reject_draft(
    draft_id: str,
    body: ApprovalRequest,
    session: Session = Depends(get_session),
) -> ApprovalResponse:
    """Record a lawyer's rejection of the current draft version."""
    with transactional(session):
        decision = workflow.reject_current_draft(
            session,
            draft_id=draft_id,
            reviewer_id=body.reviewer_id,
        )
        session.commit()
    return ApprovalResponse.model_validate(decision)
