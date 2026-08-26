"""Organisations API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_session
from app.api.schemas.organisations import OrganisationResponse
from app.models.organisation import Organisation

router = APIRouter(
    prefix="/organisations",
    tags=["organisations"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[OrganisationResponse])
def list_active_organisations(
    session: Session = Depends(get_session),
) -> list[OrganisationResponse]:
    """List active organisations."""
    rows = session.scalars(
        select(Organisation)
        .where(Organisation.status == "active")
        .order_by(Organisation.name)
    ).all()
    return [OrganisationResponse.model_validate(row) for row in rows]
