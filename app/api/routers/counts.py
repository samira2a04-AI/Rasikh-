"""Counts panel endpoints (FR-034)."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_optional_current_user
from app.api.dependencies import get_session
from app.api.schemas import CountsResponse
from app.models import Draft, MatterAssignment, Obligation, Request, User

router = APIRouter(prefix="/counts", tags=["counts"])


@router.get("", response_model=CountsResponse)
def get_counts(
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> CountsResponse:
    """Return at-a-glance operational status for the firm."""
    req_stmt = select(Request.status).select_from(Request)
    draft_stmt = select(Draft.approval_state).select_from(Draft)
    obl_stmt = select(Obligation.band).select_from(Obligation)
    awaiting_stmt = select(func.count()).select_from(Draft).where(
        Draft.approval_state == "awaiting_approval"
    )

    if current_user and current_user.member_id:
        assigned_orgs_subquery = select(MatterAssignment.org_id).where(
            MatterAssignment.member_id == current_user.member_id
        )
        assigned_requests_subquery = select(Request.request_id).where(
            (Request.org_id.in_(assigned_orgs_subquery)) | (Request.org_id.is_(None))
        )
        req_stmt = req_stmt.where(
            (Request.org_id.in_(assigned_orgs_subquery)) | (Request.org_id.is_(None))
        )
        draft_stmt = draft_stmt.where(Draft.request_id.in_(assigned_requests_subquery))
        obl_stmt = obl_stmt.where(Obligation.org_id.in_(assigned_orgs_subquery))
        awaiting_stmt = awaiting_stmt.where(Draft.request_id.in_(assigned_requests_subquery))

    status_counts = Counter(
        row[0] for row in session.execute(req_stmt).all()
    )
    state_counts = Counter(
        row[0] for row in session.execute(draft_stmt).all()
    )
    band_counts = Counter(
        row[0] for row in session.execute(obl_stmt).all()
    )
    awaiting = session.execute(awaiting_stmt).scalar_one()

    return CountsResponse(
        requests_by_status=dict(status_counts),
        drafts_by_approval_state=dict(state_counts),
        obligations_by_band=dict(band_counts),
        items_awaiting_approval=awaiting,
    )
