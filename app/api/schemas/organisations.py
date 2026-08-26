"""Pydantic schemas for the organisations API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OrganisationResponse(BaseModel):
    """Response model for a stored organisation."""

    model_config = ConfigDict(from_attributes=True)

    org_id: str
    name: str
    sector: str
    type: str
    status: str
