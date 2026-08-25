"""Authorization tests: endpoint protection, roles, and access rules.

Covers:
- unauthenticated access to protected endpoints -> 401
- authenticated member access to business endpoints -> success
- admin-only operations rejected for members -> 403
- role cannot be self-assigned through registration
- public/system endpoints remain public
"""

from __future__ import annotations

import uuid

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.security import ALGORITHM, create_access_token, hash_password
from app.database.connection import SessionLocal
from app.main import app
from app.models import Request, User

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _cleanup_user(email: str) -> None:
    with SessionLocal() as session:
        session.execute(delete(User).where(User.email == email))
        session.commit()


def _create_role_user(role: str) -> tuple[str, str]:
    """Create a user with the given role; return (token, email) for cleanup."""
    email = f"authz-{role}-{uuid.uuid4().hex[:8]}@rasikh.test"
    with SessionLocal() as session:
        user = User(email=email, hashed_password=hash_password("password-1"), role=role)
        session.add(user)
        session.commit()
        session.refresh(user)
        token = create_access_token(str(user.id))
    return token, email


@pytest.fixture()
def member_token():
    token, email = _create_role_user("member")
    yield token
    _cleanup_user(email)


@pytest.fixture()
def admin_token():
    token, email = _create_role_user("admin")
    yield token
    _cleanup_user(email)


def _seeded_request_id() -> str:
    """Return one existing seeded request id (row is not modified)."""
    with SessionLocal() as session:
        request_id = session.scalars(select(Request.request_id).limit(1)).first()
    assert request_id is not None
    return str(request_id)


# ---------------------------------------------------------------------------
# 401 — unauthenticated access to protected endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/requests"),
        ("get", "/requests/some-id"),
        ("post", "/requests/some-id/review"),
        ("post", "/requests/some-id/drafts"),
        ("get", "/requests/some-id/drafts"),
        ("get", "/requests/some-id/history"),
        ("post", "/drafts/some-draft/approve"),
        ("post", "/obligations/sweep"),
    ],
)
def test_protected_endpoints_reject_anonymous_requests(method, path):
    if method == "get":
        response = client.get(path)
    else:
        response = client.post(path, json={})
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# Public endpoints remain public
# ---------------------------------------------------------------------------


def test_health_and_counts_and_auth_remain_public():
    assert client.get("/health").status_code == 200
    assert client.get("/counts").status_code == 200
    # Reaches validation (422), NOT authentication (401) — the route is open.
    register_attempt = client.post(
        "/auth/register",
        json={"email": "x", "password": "y"},
    )
    assert register_attempt.status_code == 422


# ---------------------------------------------------------------------------
# Authenticated member access to business endpoints
# ---------------------------------------------------------------------------


def test_member_can_read_requests(member_token):
    request_id = _seeded_request_id()
    response = client.get(f"/requests/{request_id}", headers=_auth(member_token))
    assert response.status_code == 200, response.text
    assert response.json()["request_id"] == request_id


def test_member_can_list_drafts_for_a_request(member_token):
    request_id = _seeded_request_id()
    response = client.get(f"/requests/{request_id}/drafts", headers=_auth(member_token))
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Roles: admin-only operations
# ---------------------------------------------------------------------------


def test_sweep_forbidden_for_member(member_token):
    response = client.post(
        "/obligations/sweep",
        headers=_auth(member_token),
        json={"reference_date": "2026-07-01"},
    )
    assert response.status_code == 403, response.text
    assert "permission" in response.json()["detail"]


def test_sweep_allowed_for_admin(admin_token):
    response = client.post(
        "/obligations/sweep",
        headers=_auth(admin_token),
        json={
            "reference_date": "2025-01-01",  # far in the past: nothing becomes overdue
            "org_id": "ORG-1007",
            "owner_id": "L-04",
        },
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Role integrity
# ---------------------------------------------------------------------------


def test_registration_cannot_self_assign_admin_role():
    email = f"escalation-{uuid.uuid4().hex[:8]}@rasikh.test"
    try:
        response = client.post(
            "/auth/register",
            json={"email": email, "password": "password-1", "role": "admin"},
        )
        assert response.status_code == 201, response.text
        # Extra fields are ignored: the account must be a plain member.
        with SessionLocal() as session:
            user = session.execute(select(User).where(User.email == email)).scalar_one()
            assert user.role == "member"
    finally:
        _cleanup_user(email)


def test_unknown_role_value_is_rejected_by_database_constraint():
    with SessionLocal() as session:
        bad = User(
            email=f"bad-role-{uuid.uuid4().hex[:8]}@rasikh.test",
            hashed_password=hash_password("password-1"),
            role="superadmin",
        )
        session.add(bad)
        try:
            session.commit()
        except Exception:
            session.rollback()  # expected: ck_users_role rejects the value
        else:
            session.delete(bad)
            session.commit()
            pytest.fail("invalid role should have been rejected by ck_users_role")


# ---------------------------------------------------------------------------
# Token forgery / deactivated accounts
# ---------------------------------------------------------------------------


def test_forged_token_with_wrong_secret_is_rejected():
    forged = pyjwt.encode({"sub": "9999"}, "attacker-secret", algorithm=ALGORITHM)
    response = client.get(
        "/requests/some-id/drafts",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 401, response.text


def test_deactivated_user_token_is_rejected():
    token, email = _create_role_user("member")
    try:
        with SessionLocal() as session:
            user = session.execute(select(User).where(User.email == email)).scalar_one()
            user.is_active = False
            session.commit()
        protected = client.get(
            "/requests/some-id/drafts",
            headers=_auth(token),
        )
        # A deactivated account's token no longer grants access (401, not 403).
        assert protected.status_code == 401, protected.text
    finally:
        _cleanup_user(email)
