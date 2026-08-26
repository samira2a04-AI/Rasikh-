"""Pydantic schemas for the contract review API (FR-008–FR-013, FR-021, FR-022)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReviewRequest(BaseModel):
    """Trigger a contract review for an already-submitted request."""

    member_id: str
    org_id: str
    contract_id: Optional[str] = None
    reference_date: Optional[date] = None
    suppressed_obligation_ids: Optional[list[str]] = None


class CitationResponse(BaseModel):
    """A citation linking a finding to a real source clause."""

    model_config = ConfigDict(from_attributes=True)

    citation_id: UUID
    source_type: str
    contract_clause_id: Optional[UUID] = None
    standard_clause_id: Optional[UUID] = None


class FindingResponse(BaseModel):
    """A single grounded (or ungrounded) finding from a review."""

    model_config = ConfigDict(from_attributes=True)

    finding_id: UUID
    checklist_area: Optional[str] = None
    statement: str
    grounded: bool
    risk_rating: Optional[str] = None
    sharia_sensitive_flag: bool
    tricky_case_type: Optional[str] = None
    citations: list[CitationResponse] = []
    status: str = "open"
    reviewed_by: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None


class FindingReviewRequest(BaseModel):
    """Request to update a finding's human-review status."""

    status: str = "reviewed"
    reviewer_notes: Optional[str] = None


class EscalationResponse(BaseModel):
    """An escalation produced by the obligation sweep."""

    model_config = ConfigDict(from_attributes=True)

    escalation_id: UUID
    obligation_id: Optional[str] = None
    request_id: Optional[str] = None
    reason: str
    routed_to_id: str


class ObligationResponse(BaseModel):
    """An obligation snapshot from the sweep."""

    model_config = ConfigDict(from_attributes=True)

    obligation_id: str
    org_id: str
    owner_id: str
    due_date: date
    stored_band: str
    computed_band: Optional[str] = None


class ReviewResponse(BaseModel):
    """Full result of a contract review workflow run."""

    request_id: str
    access_decision: str
    engine: Optional[str] = None
    findings: list[FindingResponse]
    obligations: list[ObligationResponse]
    escalations: list[EscalationResponse]
