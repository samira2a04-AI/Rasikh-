"""Pydantic schemas for the request intake API (FR-001, FR-002)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

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


class RequestResolve(BaseModel):
    """Resolve an insufficient request by providing the missing classification."""

    org_id: str
    request_type: str = Field(
        description="contract_review / consultation / meeting_prep / obligation_check"
    )


class RequestResponse(BaseModel):
    """Response model for a stored request."""

    model_config = ConfigDict(from_attributes=True)

    request_id: str
    requester_id: str
    org_id: Optional[str] = None
    request_type: Optional[str] = None
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Unified request view (read-only aggregation of a request's outputs)
# ---------------------------------------------------------------------------

class DraftSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_id: UUID
    version: int
    approval_state: str
    content: str
    created_at: datetime
    updated_at: datetime


class ApprovalSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approval_decision_id: UUID
    draft_id: UUID
    reviewer_id: str
    decision: str
    draft_version: int
    decided_at: datetime


class AccessDecisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_decision_id: UUID
    outcome: str
    basis: str
    member_id: str
    org_id: str
    decided_at: datetime


class CitationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    citation_id: UUID
    source_type: str
    contract_clause_id: Optional[UUID] = None
    standard_clause_id: Optional[UUID] = None
    clause_reference: Optional[str] = None


class FindingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_id: UUID
    statement: str
    grounded: bool
    risk_rating: Optional[str] = None
    sharia_sensitive_flag: bool
    citations: list[CitationSummary] = []


class ObligationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    obligation_id: str
    type: str
    description: str
    due_date: date
    band: str
    owner_id: str


class EscalationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    escalation_id: UUID
    reason: str
    routed_to_id: str
    obligation_id: Optional[str] = None
    created_at: datetime


class SourceSummary(BaseModel):
    """A source document (contract) associated with the request's organisation."""

    contract_id: str
    title: str


class RequestViewCounts(BaseModel):
    drafts: int
    approvals: int
    findings: int
    obligations: int
    escalations: int


class AnalysisRunSummary(BaseModel):
    """The latest completed analysis run for a request (the real AI result)."""

    model_config = ConfigDict(from_attributes=True)

    analysis_run_id: UUID
    status: str
    engine: Optional[str] = None
    summary: Optional[str] = None
    finding_count: int
    high_severity_count: int
    grounded_count: int
    ungrounded_count: int
    created_at: datetime
    completed_at: Optional[datetime] = None


class RequestViewResponse(BaseModel):
    """Unified request-centred view: the request plus everything derived from it."""

    request: RequestResponse
    decision: Optional[str] = None
    answer: Optional[str] = None
    analysis: Optional[AnalysisRunSummary] = None
    access_decisions: list[AccessDecisionSummary] = []
    drafts: list[DraftSummary] = []
    approvals: list[ApprovalSummary] = []
    findings: list[FindingSummary] = []
    obligations: list[ObligationSummary] = []
    escalations: list[EscalationSummary] = []
    sources: list[SourceSummary] = []
    counts: RequestViewCounts


class RequestRegistryRow(BaseModel):
    """One row of the request registry: a request plus deterministic counts."""

    request: RequestResponse
    decision: Optional[str] = None
    has_answer: bool
    draft_count: int
    approval_count: int
    finding_count: int
    obligation_count: int
    # Status of the latest AnalysisRun ('running'/'completed'/'failed'), or
    # None when the request has never been analysed.
    analysis_status: Optional[str] = None
