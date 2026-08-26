"""Request intake endpoints (FR-001, FR-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import CurrentUser, get_current_user
from app.api.dependencies import get_session, transactional
from app.api.schemas.requests import (
    AnalysisRunSummary,
    ApprovalSummary,
    DraftSummary,
    EscalationSummary,
    FindingSummary,
    ObligationSummary,
    RequestRegistryRow,
    RequestResolve,
    RequestResponse,
    RequestSubmit,
    RequestViewCounts,
    RequestViewResponse,
    SourceSummary,
)
from app.models import (
    AnalysisRun,
    ApprovalDecision,
    Contract,
    Draft,
    Escalation,
    Finding,
    Obligation,
    Request,
)
from app.services import analysis_run, request_intake, workflow

router = APIRouter(prefix="/requests", tags=["requests"], dependencies=[Depends(get_current_user)])


@router.get("/registry", response_model=list[RequestRegistryRow])
def request_registry(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[RequestRegistryRow]:
    """Request registry: every request with deterministic output counts.

    Obligations are organisation-scoped (Obligation has no request_id), so a
    request's obligation count is the count of its organisation's obligations.
    ``has_answer`` is True when the request has at least one draft (the AI's
    drafted output) — no separate answer entity exists.
    """
    rows = session.scalars(
        select(Request)
        .order_by(Request.created_at.desc(), Request.request_id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    registry: list[RequestRegistryRow] = []
    for row in rows:
        draft_count = (
            session.query(Draft).filter(Draft.request_id == row.request_id).count()
        )
        approval_count = (
            session.query(ApprovalDecision)
            .join(Draft, ApprovalDecision.draft_id == Draft.draft_id)
            .filter(Draft.request_id == row.request_id)
            .count()
        )
        finding_count = (
            session.query(Finding)
            .filter(Finding.request_id == row.request_id)
            .count()
        )
        obligation_count = (
            session.query(Obligation)
            .filter(Obligation.org_id == row.org_id)
            .count()
            if row.org_id
            else 0
        )
        latest_run = (
            session.query(AnalysisRun)
            .filter(AnalysisRun.request_id == row.request_id)
            .order_by(AnalysisRun.created_at.desc())
            .first()
        )
        registry.append(
            RequestRegistryRow(
                request=RequestResponse.model_validate(row),
                has_answer=draft_count > 0,
                draft_count=draft_count,
                approval_count=approval_count,
                finding_count=finding_count,
                obligation_count=obligation_count,
                analysis_status=latest_run.status if latest_run else None,
            )
        )
    return registry


@router.get("/{request_id}/view", response_model=RequestViewResponse)
def get_request_view(
    request_id: str,
    session: Session = Depends(get_session),
) -> RequestViewResponse:
    """Unified request-centred view of one request and all its outputs."""
    request = session.get(Request, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")

    drafts = list(
        session.scalars(
            select(Draft)
            .where(Draft.request_id == request_id)
            .order_by(Draft.version.desc())
        ).all()
    )
    approvals = list(
        session.scalars(
            select(ApprovalDecision)
            .join(Draft, ApprovalDecision.draft_id == Draft.draft_id)
            .where(Draft.request_id == request_id)
            .order_by(ApprovalDecision.decided_at.desc())
        ).all()
    )
    findings = list(
        session.scalars(
            select(Finding).where(Finding.request_id == request_id)
        ).all()
    )
    escalations = list(
        session.scalars(
            select(Escalation).where(Escalation.request_id == request_id)
        ).all()
    )
    obligations = (
        list(
            session.scalars(
                select(Obligation)
                .where(Obligation.org_id == request.org_id)
                .order_by(Obligation.due_date)
            ).all()
        )
        if request.org_id
        else []
    )
    sources = (
        list(session.scalars(select(Contract).where(Contract.org_id == request.org_id)).all())
        if request.org_id
        else []
    )

    # Phase 1: the AI result is the latest COMPLETED AnalysisRun's summary —
    # never a draft. Drafts are a separate human work product.
    latest_run = analysis_run.latest_completed_run(session, request_id=request_id)
    answer = latest_run.summary if latest_run is not None else None

    return RequestViewResponse(
        request=RequestResponse.model_validate(request),
        answer=answer,
        analysis=(
            AnalysisRunSummary.model_validate(latest_run)
            if latest_run is not None
            else None
        ),
        drafts=[DraftSummary.model_validate(d) for d in drafts],
        approvals=[ApprovalSummary.model_validate(a) for a in approvals],
        findings=[FindingSummary.model_validate(f) for f in findings],
        obligations=[ObligationSummary.model_validate(o) for o in obligations],
        escalations=[EscalationSummary.model_validate(e) for e in escalations],
        sources=[SourceSummary(contract_id=c.contract_id, title=c.title) for c in sources],
        counts=RequestViewCounts(
            drafts=len(drafts),
            approvals=len(approvals),
            findings=len(findings),
            obligations=len(obligations),
            escalations=len(escalations),
        ),
    )


@router.get("", response_model=list[RequestResponse])
def list_requests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[RequestResponse]:
    """List requests, newest first (simple limit/offset pagination)."""
    rows = session.scalars(
        select(Request)
        .order_by(Request.created_at.desc(), Request.request_id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [RequestResponse.model_validate(row) for row in rows]


@router.post("", response_model=RequestResponse, status_code=201)
def submit_request(
    body: RequestSubmit,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> RequestResponse:
    """Submit a new request and classify it.

    When ``body.requester_id`` is omitted, it is derived from the authenticated
    user's mapped team member (``current_user.member_id``). A mapped account
    always resolves; an unmapped account cannot author a request. An explicitly
    supplied ``requester_id`` is still honoured and validated at intake.
    """
    requester_id = body.requester_id
    if requester_id is None:
        requester_id = current_user.member_id
        if requester_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "no requester_id supplied and the authenticated account is "
                    "not mapped to a firm team member"
                ),
            )

    with transactional(session):
        if body.request_type is not None:
            request = workflow.intake_and_classify(
                session,
                request_id=body.request_id,
                requester_id=requester_id,
                raw_content=body.raw_content,
                org_id=body.org_id,
                request_type=body.request_type,
                created_at=body.created_at,
            )
        else:
            try:
                request = workflow.auto_intake_and_classify(
                    session,
                    request_id=body.request_id,
                    requester_id=requester_id,
                    raw_content=body.raw_content,
                    org_id=body.org_id,
                    created_at=body.created_at,
                )
            except workflow.WorkflowStageError as exc:
                cause = getattr(exc, "__cause__", None)
                if cause is not None and getattr(cause, "code", None) == 429:
                    raise HTTPException(
                        status_code=503,
                        detail="AI classification is temporarily unavailable. Please try again shortly.",
                    ) from exc
                raise
        session.commit()
    return RequestResponse.model_validate(request)


@router.get("/{request_id}", response_model=RequestResponse)
def get_request(
    request_id: str,
    session: Session = Depends(get_session),
) -> RequestResponse:
    """Return a single request by id."""
    request = session.get(Request, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id {request_id!r}")
    return RequestResponse.model_validate(request)


@router.patch("/{request_id}/resolve", response_model=RequestResponse)
def resolve_request(
    request_id: str,
    body: RequestResolve,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> RequestResponse:
    """Manually resolve a request left in 'insufficient' status."""
    if current_user.member_id is None:
        raise HTTPException(
            status_code=400,
            detail="Authenticated account is not mapped to a firm team member.",
        )
    with transactional(session):
        request = workflow.resolve_insufficient_request(
            session,
            request_id=request_id,
            member_id=current_user.member_id,
            org_id=body.org_id,
            request_type=body.request_type,
        )
        session.commit()
    return RequestResponse.model_validate(request)
