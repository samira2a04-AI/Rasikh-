"""Contract review endpoints (FR-008–FR-013, FR-021, FR-022)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_session, transactional
from app.api.schemas import (
    CitationResponse,
    EscalationResponse,
    FindingResponse,
    ObligationResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.models import Request
from app.services import workflow

router = APIRouter(prefix="/requests", tags=["review"], dependencies=[Depends(get_current_user)])


def _build_review_response(request_id: str, result) -> ReviewResponse:
    """Convert workflow ORM results into a Pydantic response while the
    session is still open (so relationship lazy-loads still work)."""
    findings = []
    for finding in result.findings:
        citations = [
            CitationResponse.model_validate(c) for c in finding.citations
        ]
        findings.append(
            FindingResponse(
                finding_id=str(finding.finding_id),
                checklist_area=finding.checklist_area,
                statement=finding.statement,
                grounded=finding.grounded,
                risk_rating=finding.risk_rating,
                sharia_sensitive_flag=finding.sharia_sensitive_flag,
                tricky_case_type=finding.tricky_case_type,
                citations=citations,
            )
        )

    obligations: list[ObligationResponse] = []
    escalations: list[EscalationResponse] = []
    sweep = result.sweep_result
    if sweep is not None:
        for snap in sweep.inspected:
            obligations.append(
                ObligationResponse(
                    obligation_id=snap.obligation_id,
                    org_id=snap.org_id,
                    owner_id=snap.owner_id,
                    due_date=snap.due_date,
                    stored_band=snap.stored_band,
                    computed_band=snap.computed_band,
                )
            )
        for esc in sweep.escalations_created:
            escalations.append(
                EscalationResponse(
                    escalation_id=str(esc.escalation_id),
                    obligation_id=esc.obligation_id,
                    request_id=None,
                    reason=esc.reason,
                    routed_to_id=esc.routed_to_id,
                )
            )

    return ReviewResponse(
        request_id=request_id,
        access_decision=result.access_decision.outcome,
        findings=findings,
        obligations=obligations,
        escalations=escalations,
    )


@router.post("/{request_id}/review", response_model=ReviewResponse)
def run_review(
    request_id: str,
    body: ReviewRequest,
    session: Session = Depends(get_session),
) -> ReviewResponse:
    """Run the contract review workflow for a submitted request."""
    if session.get(Request, request_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")
    with transactional(session):
        result = workflow.run_review(
            session,
            request_id=request_id,
            member_id=body.member_id,
            org_id=body.org_id,
            contract_id=body.contract_id,
            reference_date=body.reference_date,
            suppressed_obligation_ids=set(body.suppressed_obligation_ids or []),
        )
        session.commit()
        response = _build_review_response(request_id, result)
    return response
