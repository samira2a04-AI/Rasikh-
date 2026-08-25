"""Obligation endpoints (FR-016–FR-018)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth_dependencies import require_admin
from app.api.dependencies import get_session, transactional
from app.api.schemas import (
    EscalationCreatedResponse,
    ObligationSnapshotResponse,
    ObligationSweepRequest,
    ObligationSweepResponse,
)
from app.services import workflow

router = APIRouter(prefix="/obligations", tags=["obligations"])


@router.post(
    "/sweep",
    response_model=ObligationSweepResponse,
    dependencies=[Depends(require_admin)],
)
def sweep_obligations(
    body: ObligationSweepRequest,
    session: Session = Depends(get_session),
) -> ObligationSweepResponse:
    """Run the obligation threshold sweep and create required escalations."""
    with transactional(session):
        result = workflow.run_obligation_sweep(
            session,
            reference_date=body.reference_date,
            org_id=body.org_id,
            owner_id=body.owner_id,
            suppressed_obligation_ids=set(body.suppressed_obligation_ids or []),
        )
        session.commit()

    return ObligationSweepResponse(
        reference_date=result.reference_date,
        inspected=[
            ObligationSnapshotResponse(
                obligation_id=s.obligation_id,
                org_id=s.org_id,
                owner_id=s.owner_id,
                due_date=s.due_date,
                stored_band=s.stored_band,
                computed_band=s.computed_band,
            )
            for s in result.inspected
        ],
        on_track=list(result.on_track),
        reminder=list(result.reminder),
        urgent=list(result.urgent),
        overdue=list(result.overdue),
        suppressed=list(result.suppressed),
        escalations_created=[
            EscalationCreatedResponse(
                escalation_id=str(e.escalation_id),
                obligation_id=e.obligation_id,
                reason=e.reason,
                routed_to_id=e.routed_to_id,
            )
            for e in result.escalations_created
        ],
        already_escalated=list(result.already_escalated),
        band_drift=list(result.band_drift),
    )
