"""Pydantic schemas for the draft API (FR-028, APR-001–APR-003)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DraftCreate(BaseModel):
    """Create a new draft version for a request."""

    content: str
    created_at: Optional[datetime] = None


class DraftResponse(BaseModel):
    """Response model for a stored draft."""

    model_config = ConfigDict(from_attributes=True)

    draft_id: UUID
    request_id: str
    content: str
    version: int
    approval_state: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
