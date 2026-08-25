"""Pydantic schemas for the request intake API (FR-001, FR-002)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RequestSubmit(BaseModel):
    """Submit a new request and classify it.

    ``requester_id`` is optional: when omitted, the backend derives it from the
    authenticated user's mapped team member (``users.member_id``). It may still
    be supplied explicitly (e.g. by service/API callers) and is validated
    against ``team_member`` at intake.
    """

    request_id: str
    requester_id: Optional[str] = None
    raw_content: str
    org_id: Optional[str] = None
    request_type: Optional[str] = Field(
        default=None,
        description="contract_review / consultation / meeting_prep / obligation_check",
    )
    created_at: Optional[datetime] = None


class RequestResponse(BaseModel):
    """Response model for a stored request."""

    model_config = ConfigDict(from_attributes=True)

    request_id: str
    requester_id: str
    org_id: Optional[str] = None
    request_type: Optional[str] = None
    status: str
    created_at: datetime
