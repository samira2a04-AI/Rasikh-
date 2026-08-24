"""Pydantic schemas for the history API (FR-033)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    """A single append-only audit event."""

    model_config = ConfigDict(from_attributes=True)

    audit_event_id: UUID
    request_id: Optional[str] = None
    event_type: str
    actor_id: Optional[str] = None
    detail_reference: Optional[str] = None
    detail_json: Optional[dict] = None
    occurred_at: datetime


class RequestHistoryResponse(BaseModel):
    """Full lifecycle history of a request."""

    request_id: str
    events: list[AuditEventResponse]
