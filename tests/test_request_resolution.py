"""Tests for manual request resolution (insufficient -> classified)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.main import app
from app.models import AuditEvent, Request, Organisation, User
from app.services import request_intake
from app.services.access_control import record_access_decision

import uuid

client = TestClient(app)

def _auth_headers() -> dict[str, str]:
    response = client.post(
        "/auth/login", json={"email": "lawyer@rasikh.local", "password": "Demo1234!"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def test_successful_resolution_workflow():
    """Test successfully assigning an organisation and request type to an insufficient request."""
    headers = _auth_headers()
    req_id = f"REQ-TEST-{uuid.uuid4().hex[:8]}"
    
    with SessionLocal() as session:
        # 1. Setup an insufficient request
        req = request_intake.submit_request(
            session,
            request_id=req_id,
            requester_id="L-01",
            raw_content="Review this",
        )
        req.status = "insufficient"
        session.commit()

    # 2. Setup an organisation the user has access to
    # L-01 has access to ORG-1003 by default from the test seeds.
    # We will use ORG-1003 and assign it.
    response = client.patch(
        f"/requests/{req_id}/resolve",
        json={"org_id": "ORG-1003", "request_type": "contract_review"},
        headers=headers,
    )
    print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["org_id"] == "ORG-1003"
    assert data["request_type"] == "contract_review"
    assert data["status"] == "classified"

    # Verify audit event
    with SessionLocal() as session:
        events = session.query(AuditEvent).filter_by(request_id=req_id).order_by(AuditEvent.occurred_at).all()
        assert events[-1].event_type == "manual_classification"
        assert events[-1].detail_json["org_id"] == "ORG-1003"


def test_resolve_with_unauthorized_org():
    """Test resolving a request with an organisation the user doesn't have access to."""
    # L-01 is a partner and has access to all orgs. Use L-06 instead.
    # L-06 does NOT have access to ORG-1003.
    client.post("/auth/register", json={"email": "test-res-unauth@rasikh.local", "password": "correct-horse-1"})
    with SessionLocal() as session:
        user = session.query(User).filter_by(email="test-res-unauth@rasikh.local").first()
        user.member_id = "L-06"
        session.commit()
        
    response = client.post(
        "/auth/login", json={"email": "test-res-unauth@rasikh.local", "password": "correct-horse-1"}
    )
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    req_id = f"REQ-TEST-{uuid.uuid4().hex[:8]}"

    with SessionLocal() as session:
        req = request_intake.submit_request(
            session,
            request_id=req_id,
            requester_id="L-06",
            raw_content="Review this",
        )
        req.status = "insufficient"
        session.commit()

    # User L-06 doesn't have access to ORG-1003
    response = client.patch(
        f"/requests/{req_id}/resolve",
        json={"org_id": "ORG-1003", "request_type": "contract_review"},
        headers=headers,
    )
    assert response.status_code == 403
    assert "no_matter_assignment" in response.json()["detail"]


def test_resolve_with_invalid_request_type():
    """Test resolving a request with an invalid request type."""
    headers = _auth_headers()
    req_id = f"REQ-TEST-{uuid.uuid4().hex[:8]}"

    with SessionLocal() as session:
        req = request_intake.submit_request(
            session,
            request_id=req_id,
            requester_id="L-01",
            raw_content="Review this",
        )
        req.status = "insufficient"
        session.commit()

    response = client.patch(
        f"/requests/{req_id}/resolve",
        json={"org_id": "ORG-1003", "request_type": "invalid_type"},
        headers=headers,
    )
    assert response.status_code == 400


def test_resolve_inactive_organisation():
    """Test resolving a request with an inactive organisation."""
    headers = _auth_headers()
    req_id = f"REQ-TEST-{uuid.uuid4().hex[:8]}"

    with SessionLocal() as session:
        req = request_intake.submit_request(
            session,
            request_id=req_id,
            requester_id="L-01",
            raw_content="Review this",
        )
        req.status = "insufficient"
        session.commit()

    # ORG-1009 is dormant
    response = client.patch(
        f"/requests/{req_id}/resolve",
        json={"org_id": "ORG-1009", "request_type": "contract_review"},
        headers=headers,
    )
    assert response.status_code == 400


def test_resolve_already_classified_request():
    """Test resolving a request that is already classified."""
    headers = _auth_headers()
    req_id = f"REQ-TEST-{uuid.uuid4().hex[:8]}"

    with SessionLocal() as session:
        req = request_intake.submit_request(
            session,
            request_id=req_id,
            requester_id="L-01",
            raw_content="Review this",
        )
        req.status = "classified"
        session.commit()

    response = client.patch(
        f"/requests/{req_id}/resolve",
        json={"org_id": "ORG-1003", "request_type": "contract_review"},
        headers=headers,
    )
    assert response.status_code == 400
