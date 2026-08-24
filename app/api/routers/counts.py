"""Counts panel endpoints (FR-034)."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.api.schemas import CountsResponse
from app.models import Draft, Obligation, Request

router = APIRouter(prefix="/counts", tags=["counts"])


@router.get("", response_model=CountsResponse)
def get_counts(
    session: Session = Depends(get_session),
) -> CountsResponse:
    """Return at-a-glance operational status for the firm."""
    status_counts = Counter(
        row[0]
        for row in session.execute(
            select(Request.status).select_from(Request)
        ).all()
    )
    state_counts = Counter(
        row[0]
        for row in session.execute(
            select(Draft.approval_state).select_from(Draft)
        ).all()
    )
    band_counts = Counter(
        row[0]
        for row in session.execute(
            select(Obligation.band).select_from(Obligation)
        ).all()
    )
    awaiting = session.execute(
        select(func.count()).select_from(Draft).where(
            Draft.approval_state == "awaiting_approval"
        )
    ).scalar_one()

    return CountsResponse(
        requests_by_status=dict(status_counts),
        drafts_by_approval_state=dict(state_counts),
        obligations_by_band=dict(band_counts),
        items_awaiting_approval=awaiting,
    )
