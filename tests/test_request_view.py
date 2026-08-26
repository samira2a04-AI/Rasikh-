"""Tests for the unified request view endpoints.

GET /requests/registry            — deterministic per-request output counts
GET /requests/{request_id}/view   — unified request-centred aggregation

Uses the same authenticated TestClient pattern as tests/test_api.py against
the real seeded PostgreSQL database; every created row is cleaned up.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.connection import SessionLocal
from app.main import app
from app.models import Draft, Request, User

from tests.test_api import client  # authenticated TestClient


def _cleanup(request_id: str) -> None:
    with SessionLocal() as session:
        request = session.get(Request, request_id)
        if request is not None:
            for draft in session.scalars(
                select(Draft).where(Draft.request_id == request_id)
            ).all():
                session.delete(draft)
            session.delete(request)
            session.commit()


def _make_request(request_id: str, org_id: str | None = "ORG-1007") -> None:
    with SessionLocal() as session:
        session.add(
            Request(
                request_id=request_id,
                requester_id="L-01",
                org_id=org_id,
                request_type="contract_review",
                raw_content="test unified view",
                status="classified",
            )
        )
        session.commit()


def test_registry_lists_requests_with_counts() -> None:
    resp = client.get("/requests/registry?limit=5")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    if rows:
        row = rows[0]
        assert {"request", "has_answer", "draft_count", "approval_count",
                "finding_count", "obligation_count"} <= set(row)
        assert isinstance(row["draft_count"], int)


def test_request_view_aggregates_outputs() -> None:
    request_id = f"REQ-VIEW-{uuid.uuid4().hex[:8]}"
    try:
        _make_request(request_id)
        with SessionLocal() as session:
            session.add(
                Draft(
                    draft_id=uuid.uuid4(),
                    request_id=request_id,
                    content="Drafted answer content",
                    version=1,
                    approval_state="awaiting_approval",
                )
            )
            session.commit()

        resp = client.get(f"/requests/{request_id}/view")
        assert resp.status_code == 200
        body = resp.json()

        assert body["request"]["request_id"] == request_id
        assert body["request"]["request_type"] == "contract_review"
        # Phase 1: a Draft is never the AI result. Without an AnalysisRun,
        # there is no AI answer even when drafts exist.
        assert body["answer"] is None
        assert body["analysis"] is None
        assert body["counts"]["drafts"] == 1
        assert len(body["drafts"]) == 1
        # ORG-1007 has seeded contracts and obligations.
        assert body["counts"]["obligations"] == len(body["obligations"])
        assert body["counts"]["obligations"] > 0
        assert {s["contract_id"] for s in body["sources"]} >= {"C-01"}
    finally:
        _cleanup(request_id)


def test_request_view_unknown_request_404() -> None:
    resp = client.get("/requests/DOES-NOT-EXIST/view")
    assert resp.status_code == 404


def test_request_view_without_drafts_has_null_answer() -> None:
    request_id = f"REQ-VIEW-{uuid.uuid4().hex[:8]}"
    try:
        _make_request(request_id)
        resp = client.get(f"/requests/{request_id}/view")
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] is None
        assert body["counts"]["drafts"] == 0
    finally:
        _cleanup(request_id)