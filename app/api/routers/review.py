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
    FindingReviewRequest,
    ObligationResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.models import Request, Finding, Escalation
from app.services import workflow, access_control, review as review_service
from sqlalchemy import select

router = APIRouter(prefix="/requests", tags=["review"], dependencies=[Depends(get_current_user)])


def _build_review_response(request_id: str, result) -> ReviewResponse:
    """Convert workflow ORM results into a Pydantic response while the
    session is still open (so relationship lazy-loads still work)."""
    findings = []
    for finding in result.findings:
        citations = [
            CitationResponse.model_validate(c) for c in finding.citations
        ]
        reviewer_name = finding.reviewer.name if getattr(finding, "reviewer", None) else finding.reviewed_by
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
                status=finding.status,
                reviewed_by=finding.reviewed_by,
                reviewed_by_name=reviewer_name,
                reviewed_at=finding.reviewed_at,
                reviewer_notes=finding.reviewer_notes,
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
    request: ReviewRequest,
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user),
) -> ReviewResponse:
    """Run contract review workflow and return the results.

    This endpoint records the access decision, retrieves documents, performs the rulebook review,
    optional obligation sweep, and persists all findings before returning a serialized response.
    """
    # Run the workflow inside a transaction so lazy-loaded relationships are available
    with transactional(session):
        result = workflow.run_review(
            session,
            request_id=request_id,
            member_id=request.member_id,
            org_id=request.org_id,
            contract_id=getattr(request, "contract_id", None),
        )
        response = _build_review_response(request_id, result)
        session.commit()
        return response

@router.get("/{request_id}/review", response_model=ReviewResponse)
def get_review(
    request_id: str,
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user),
) -> ReviewResponse:
    """Retrieve the results of a previously run contract review."""
    req = session.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")

    if not req.access_decisions:
        raise HTTPException(status_code=404, detail="No review found for this request")

    latest_decision = max(req.access_decisions, key=lambda d: d.decided_at)
    if latest_decision.outcome != "authorized":
        raise HTTPException(status_code=403, detail="Not authorized to view this review")

    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.request_id == request_id)
            .order_by(Finding.finding_id)
        ).all()
    )

    finding_responses = []
    for finding in findings:
        citations = [CitationResponse.model_validate(c) for c in finding.citations]
        reviewer_name = finding.reviewer.name if getattr(finding, "reviewer", None) else finding.reviewed_by
        finding_responses.append(
            FindingResponse(
                finding_id=str(finding.finding_id),
                checklist_area=finding.checklist_area,
                statement=finding.statement,
                grounded=finding.grounded,
                risk_rating=finding.risk_rating,
                sharia_sensitive_flag=finding.sharia_sensitive_flag,
                tricky_case_type=finding.tricky_case_type,
                citations=citations,
                status=finding.status,
                reviewed_by=finding.reviewed_by,
                reviewed_by_name=reviewer_name,
                reviewed_at=finding.reviewed_at,
                reviewer_notes=finding.reviewer_notes,
            )
        )

    escalations = list(
        session.scalars(
            select(Escalation)
            .where(Escalation.request_id == request_id)
            .order_by(Escalation.escalation_id)
        ).all()
    )

    escalation_responses = []
    for esc in escalations:
        escalation_responses.append(
            EscalationResponse(
                escalation_id=str(esc.escalation_id),
                obligation_id=esc.obligation_id,
                request_id=esc.request_id,
                reason=esc.reason,
                routed_to_id=esc.routed_to_id,
            )
        )

    return ReviewResponse(
        request_id=request_id,
        access_decision=latest_decision.outcome,
        findings=finding_responses,
        obligations=[],
        escalations=escalation_responses,
    )


@router.patch("/{request_id}/findings/{finding_id}/review", response_model=FindingResponse)
def update_finding_review(
    request_id: str,
    finding_id: str,
    body: FindingReviewRequest,
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user),
) -> FindingResponse:
    """Record human-review decisions/notes on a specific finding."""
    req = session.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")

    if not current_user.member_id:
        raise HTTPException(status_code=403, detail="Current user has no linked member account")

    if req.org_id:
        access = access_control.check_access(session, member_id=current_user.member_id, org_id=req.org_id)
        if not access.authorized:
            raise HTTPException(status_code=403, detail="Not authorized to review findings for this matter")

    with transactional(session):
        try:
            updated_finding = review_service.review_finding(
                session,
                request_id=request_id,
                finding_id=finding_id,
                reviewer_id=current_user.member_id,
                status=body.status,
                reviewer_notes=body.reviewer_notes,
            )
            session.commit()
        except review_service.ReviewPersistenceError as err:
            raise HTTPException(status_code=400, detail=str(err))

        citations = [CitationResponse.model_validate(c) for c in updated_finding.citations]
        reviewer_name = updated_finding.reviewer.name if getattr(updated_finding, "reviewer", None) else updated_finding.reviewed_by
        return FindingResponse(
            finding_id=str(updated_finding.finding_id),
            checklist_area=updated_finding.checklist_area,
            statement=updated_finding.statement,
            grounded=updated_finding.grounded,
            risk_rating=updated_finding.risk_rating,
            sharia_sensitive_flag=updated_finding.sharia_sensitive_flag,
            tricky_case_type=updated_finding.tricky_case_type,
            citations=citations,
            status=updated_finding.status,
            reviewed_by=updated_finding.reviewed_by,
            reviewed_by_name=reviewer_name,
            reviewed_at=updated_finding.reviewed_at,
            reviewer_notes=updated_finding.reviewer_notes,
        )
