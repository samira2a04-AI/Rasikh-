"""Phase 1 tests: AnalysisRun lifecycle and real AI result persistence.

Covers:
- POST /requests/{id}/review creates an AnalysisRun
- Findings created during a run carry that run's analysis_run_id
- Re-running creates distinct runs; findings stay grouped per run
- GET /requests/{id}/view exposes the latest COMPLETED run as `analysis`
  and never presents Draft content as the AI result (`answer`)
- Requests with no analysis return analysis=None
- ai_analysis_started / ai_analysis_completed audit events are recorded
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.database.connection import SessionLocal
from app.models import (
    AccessDecision,
    AuditEvent,
    AnalysisRun,
    Citation,
    Draft,
    Finding,
    Request,
)

from tests.test_api import client  # authenticated TestClient


def _cleanup(request_id: str) -> None:
    with SessionLocal() as session:
        request = session.get(Request, request_id)
        if request is None:
            return
        # Delete children explicitly: relationship-cascade nulling of
        # access_decision.request_id would violate its NOT NULL constraint.
        finding_ids = session.scalars(
            select(Finding.finding_id).where(Finding.request_id == request_id)
        ).all()
        if finding_ids:
            session.query(Citation).filter(
                Citation.finding_id.in_(finding_ids)
            ).delete(synchronize_session=False)
        for model in (Finding, Draft, AnalysisRun, AuditEvent):
            session.query(model).filter(model.request_id == request_id).delete(
                synchronize_session=False
            )
        session.query(AccessDecision).filter(
            AccessDecision.request_id == request_id
        ).delete(synchronize_session=False)
        session.delete(request)
        session.commit()


def _make_request(request_id: str) -> None:
    with SessionLocal() as session:
        session.add(
            Request(
                request_id=request_id,
                requester_id="L-01",
                org_id="ORG-1007",
                request_type="contract_review",
                raw_content="analysis run test",
                status="classified",
            )
        )
        session.commit()


def _run_review(request_id: str) -> dict:
    resp = client.post(
        f"/requests/{request_id}/review",
        json={"member_id": "L-01", "org_id": "ORG-1007"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _get_runs(request_id: str) -> list[AnalysisRun]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(AnalysisRun)
                .where(AnalysisRun.request_id == request_id)
                .order_by(AnalysisRun.created_at)
            ).all()
        )

def test_review_creates_completed_analysis_run_with_linked_findings() -> None:
    request_id = f"REQ-ARUN-{uuid.uuid4().hex[:8]}"
    try:
        _make_request(request_id)
        _run_review(request_id)

        runs = _get_runs(request_id)
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "completed"
        assert run.summary is not None and "finding" in run.summary.lower()
        assert run.completed_at is not None

        with SessionLocal() as session:
            findings = list(
                session.scalars(
                    select(Finding).where(Finding.request_id == request_id)
                ).all()
            )
            assert len(findings) > 0
            for f in findings:
                assert f.analysis_run_id == run.analysis_run_id
            for f in findings:
                if f.grounded:
                    assert (
                        session.scalar(
                            select(Citation.citation_id)
                            .where(Citation.finding_id == f.finding_id)
                            .limit(1)
                        )
                        is not None
                    )

        grounded = sum(1 for f in findings if f.grounded)
        assert run.grounded_count == grounded
        assert run.ungrounded_count == len(findings) - grounded
        assert run.finding_count == len(findings)
    finally:
        _cleanup(request_id)


def test_rerun_creates_second_run_and_findings_stay_grouped() -> None:
    request_id = f"REQ-ARUN-{uuid.uuid4().hex[:8]}"
    try:
        _make_request(request_id)
        _run_review(request_id)
        _run_review(request_id)

        runs = _get_runs(request_id)
        assert len(runs) == 2

        with SessionLocal() as session:
            findings = list(
                session.scalars(
                    select(Finding).where(Finding.request_id == request_id)
                ).all()
            )
            all_ids = {str(r.analysis_run_id) for r in runs}
            for f in findings:
                assert f.analysis_run_id is not None
                assert str(f.analysis_run_id) in all_ids
    finally:
        _cleanup(request_id)


def test_view_exposes_latest_analysis_and_never_draft_as_answer() -> None:
    request_id = f"REQ-ARUN-{uuid.uuid4().hex[:8]}"
    try:
        _make_request(request_id)
        _run_review(request_id)

        with SessionLocal() as session:
            session.add(
                Draft(
                    draft_id=uuid.uuid4(),
                    request_id=request_id,
                    content="HUMAN DRAFT CONTENT -- NOT AN AI RESULT",
                    version=1,
                    approval_state="awaiting_approval",
                )
            )
            session.commit()

        resp = client.get(f"/requests/{request_id}/view")
        assert resp.status_code == 200
        body = resp.json()

        assert body["analysis"] is not None
        analysis = body["analysis"]
        assert analysis["status"] == "completed"
        assert analysis["summary"] is not None
        assert analysis["finding_count"] > 0

        assert body["answer"] == analysis["summary"]
        assert "HUMAN DRAFT CONTENT" not in (body["answer"] or "")

        assert len(body["drafts"]) == 1
        assert body["drafts"][0]["content"] == "HUMAN DRAFT CONTENT -- NOT AN AI RESULT"
    finally:
        _cleanup(request_id)


def test_view_without_analysis_returns_null_analysis() -> None:
    request_id = f"REQ-ARUN-{uuid.uuid4().hex[:8]}"
    try:
        _make_request(request_id)
        resp = client.get(f"/requests/{request_id}/view")
        assert resp.status_code == 200
        body = resp.json()
        assert body["analysis"] is None
        assert body["answer"] is None
    finally:
        _cleanup(request_id)


def test_analysis_audit_events_recorded() -> None:
    request_id = f"REQ-ARUN-{uuid.uuid4().hex[:8]}"
    try:
        _make_request(request_id)
        _run_review(request_id)

        resp = client.get(f"/requests/{request_id}/history")
        assert resp.status_code == 200
        event_types = {e["event_type"] for e in resp.json()["events"]}
        assert "ai_analysis_started" in event_types
        assert "ai_analysis_completed" in event_types
    finally:
        _cleanup(request_id)
