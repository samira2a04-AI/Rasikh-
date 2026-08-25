"""Tests for demo-user seeding, /auth/me, and derived requester resolution.

Exercises the authenticated-user -> team-member mapping added to prepare the
application for end-to-end testing:

- Seed idempotency (running the seeder twice never duplicates or corrupts).
- /auth/me returns the mapped team member.
- POST /requests derives requester_id from the authenticated user when omitted.
- An unmapped account cannot author a request.
- Invalid credentials are rejected; protected endpoints require a token.

Uses FastAPI TestClient against the real seeded PostgreSQL database. Every test
creates uniquely-addressed users and removes them afterwards.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.security import verify_password
from app.database.connection import SessionLocal
from app.main import app
from app.models import Request, User
from scripts.seed_demo_users import DEMO_USERS, seed_demo_users

client = TestClient(app)


def _unique_email() -> str:
    return f"demo-flow-{uuid.uuid4().hex[:10]}@rasikh.test"


def _cleanup(emails: list[str], request_ids: list[str] | None = None) -> None:
    with SessionLocal() as session:
        for rid in request_ids or []:
            row = session.get(Request, rid)
            if row is not None:
                session.delete(row)
        if emails:
            session.execute(delete(User).where(User.email.in_(emails)))
        session.commit()


def _register_login(email: str, password: str = "correct-horse-1") -> dict[str, str]:
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _link_member(email: str, member_id: str) -> None:
    with SessionLocal() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one()
        user.member_id = member_id
        session.commit()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def test_seed_demo_users_is_idempotent_and_hashes_passwords() -> None:
    # Make the test self-contained regardless of prior seeding: remove the
    # fixed demo emails first, then verify that running the seeder twice
    # creates once and duplicates never. Leave them in place afterwards so
    # the demo accounts remain available for end-to-end testing.
    with SessionLocal() as session:
        session.execute(
            delete(User).where(User.email.in_([s["email"] for s in DEMO_USERS]))
        )
        session.commit()

    with SessionLocal() as session, session.begin():
        first = seed_demo_users(session)
        assert first["created"] == 2, first
        second = seed_demo_users(session)
        assert second["created"] == 0, second
        assert second["updated"] == 0, second

        for spec in DEMO_USERS:
            user = session.execute(
                select(User).where(User.email == spec["email"])
            ).scalar_one()
            assert user.hashed_password.startswith("$2"), "bcrypt hash expected"
            assert user.hashed_password != "Demo1234!"
            assert verify_password("Demo1234!", user.hashed_password)
            assert user.member_id is not None


# ---------------------------------------------------------------------------
# /auth/me and derived requester resolution
# ---------------------------------------------------------------------------


def test_me_returns_mapped_member() -> None:
    email = _unique_email()
    try:
        headers = _register_login(email)
        _link_member(email, "L-01")
        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["email"] == email
        assert body["member_id"] == "L-01"
        assert body["member"]["member_id"] == "L-01"
        assert body["member"]["name"]  # linked roster member name
    finally:
        _cleanup([email])


def test_me_returns_no_member_for_unmapped_account() -> None:
    email = _unique_email()
    try:
        headers = _register_login(email)
        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["member_id"] is None
        assert body["member"] is None
    finally:
        _cleanup([email])


def test_me_requires_authentication() -> None:
    assert client.get("/auth/me").status_code == 401


def test_post_request_derives_requester_from_authenticated_user() -> None:
    email = _unique_email()
    request_id = f"derived-{uuid.uuid4().hex[:8]}"
    try:
        headers = _register_login(email)
        _link_member(email, "L-01")
        resp = client.post(
            "/requests",
            headers=headers,
            json={
                "request_id": request_id,
                "raw_content": "Derived requester integration probe.",
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["requester_id"] == "L-01"
    finally:
        _cleanup([email], [request_id])


def test_unmapped_account_cannot_author_request() -> None:
    email = _unique_email()
    request_id = f"unmapped-{uuid.uuid4().hex[:8]}"
    try:
        headers = _register_login(email)
        resp = client.post(
            "/requests",
            headers=headers,
            json={"request_id": request_id, "raw_content": "should fail"},
        )
        assert resp.status_code == 400, resp.text
        assert "mapped to a firm team member" in resp.json()["detail"]
    finally:
        _cleanup([email], [request_id])


def test_invalid_credentials_rejected() -> None:
    email = _unique_email()
    try:
        _register_login(email)
        bad = client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-password-999"},
        )
        assert bad.status_code == 401, bad.text
        assert bad.json()["detail"] == "incorrect email or password"
    finally:
        _cleanup([email])


def test_protected_requests_require_authentication() -> None:
    assert client.get("/requests").status_code == 401

