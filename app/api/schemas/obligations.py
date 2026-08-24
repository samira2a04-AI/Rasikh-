"""Pydantic schemas for the obligation API (FR-016–FR-018)."""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ObligationSweepRequest(BaseModel):
    """Trigger an obligation sweep."""

    reference_date: date
    org_id: Optional[str] = None
    owner_id: Optional[str] = None
    suppressed_obligation_ids: Optional[list[str]] = None


class ObligationSnapshotResponse(BaseModel):
    """A single obligation's snapshot during a sweep."""

    obligation_id: str
    org_id: str
    owner_id: str
    due_date: date
    stored_band: str
    computed_band: Optional[str] = None


class EscalationCreatedResponse(BaseModel):
    """An escalation created by the sweep."""

    escalation_id: UUID
    obligation_id: str
    reason: str
    routed_to_id: str


class ObligationSweepResponse(BaseModel):
    """Full result of an obligation sweep."""

    reference_date: date
    inspected: list[ObligationSnapshotResponse]
    on_track: list[str]
    reminder: list[str]
    urgent: list[str]
    overdue: list[str]
    suppressed: list[str]
    escalations_created: list[EscalationCreatedResponse]
    already_escalated: list[str]
    band_drift: list[tuple[str, str, str]]
