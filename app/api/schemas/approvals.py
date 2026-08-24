"""Pydantic schemas for the approval API (FR-029–FR-032, APR-001–APR-005)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApprovalRequest(BaseModel):
    """Body for an approval or rejection decision."""

    reviewer_id: str


class ApprovalResponse(BaseModel):
    """Response model for a recorded approval/rejection decision."""

    model_config = ConfigDict(from_attributes=True)

    approval_decision_id: UUID
    draft_id: UUID
    reviewer_id: str
    decision: str
    draft_version: int
    decided_at: datetime
