"""Tests for GET /requests (authenticated request listing).

Runs against the seeded database. Creates a throwaway user for the Bearer
token and a temporary Request row so the list endpoint is exercised with
real data; everything is removed afterwards.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database.connection import SessionLocal
from app.main import app
from app.models import Request, User

client = TestClient(app)


def _unique_email() -> str:
    return f"req-list-{uuid.uuid4().hex[:10]}@rasikh.test"


def _cleanup_user(email: str) -> None:
    with SessionLocal() as session:
        session.execute(delete(User).where(User.email == email))
        session.commit()


def _auth_headers(email: str) -> dict[str, str]:
    response = client.post(
        "/auth/login", json={"email": email, "password": "correct-horse-1"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_list_requests_requires_authentication() -> None:
    assert client.get("/requests").status_code == 401


def test_list_requests_returns_rows_newest_first() -> None:
    email = _unique_email()
    try:
        assert (
            client.post(
                "/auth/register",
                json={"email": email, "password": "correct-horse-1"},
            ).status_code
            == 201
        )
        headers = _auth_headers(email)

        body = client.get("/requests", headers=headers)
        assert body.status_code == 200, body.text
        rows = body.json()
        assert isinstance(rows, list) and len(rows) >= 1

        first = rows[0]
        for key in (
            "request_id",
            "requester_id",
            "org_id",
            "request_type",
            "status",
            "created_at",
        ):
            assert key in first
        created = [row["created_at"] for row in rows]
        assert created == sorted(created, reverse=True)

        # Pagination is respected.
        paged = client.get(
            "/requests", headers=headers, params={"limit": 2, "offset": 0}
        )
        assert paged.status_code == 200
        assert len(paged.json()) <= 2

        unknown = client.get("/requests/does-not-exist", headers=headers)
        assert unknown.status_code == 404
    finally:
        _cleanup_user(email)


def test_list_includes_newly_submitted_request() -> None:
    email = _unique_email()
    request_id = f"list-test-{uuid.uuid4().hex[:8]}"
    try:
        assert (
            client.post(
                "/auth/register",
                json={"email": email, "password": "correct-horse-1"},
            ).status_code
            == 201
        )
        headers = _auth_headers(email)

        # Temporary request row matching the intake service contract.
        with SessionLocal() as session:
            session.add(
                Request(
                    request_id=request_id,
                    requester_id="L-01",
                    org_id=None,
                    request_type=None,
                    raw_content="List integration probe.",
                    status="intake",
                )
            )
            session.commit()

        rows = client.get("/requests", headers=headers).json()
        assert any(row["request_id"] == request_id for row in rows)
    finally:
        with SessionLocal() as session:
            row = session.get(Request, request_id)
            if row is not None:
                session.delete(row)
            session.commit()
        _cleanup_user(email)

