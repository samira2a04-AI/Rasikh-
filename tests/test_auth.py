"""Tests for authentication (/auth/register, /auth/login, JWT dependencies).

Uses FastAPI TestClient against the real PostgreSQL database. Every test
creates uniquely-addressed users and removes them afterwards so the seeded
dataset is left untouched.
"""

from __future__ import annotations

import uuid

import jwt as pyjwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.auth_dependencies import get_current_user
from app.core.security import ALGORITHM, SECRET_KEY
from app.database.connection import SessionLocal
from app.main import app
from app.models import User

client = TestClient(app)


def _unique_email() -> str:
    return f"auth-{uuid.uuid4().hex[:10]}@rasikh.test"


def _delete_user(email: str) -> None:
    with SessionLocal() as session:
        session.execute(delete(User).where(User.email == email))
        session.commit()


def _protected_probe(path: str):
    """Register a throwaway protected route to exercise get_current_user."""
    probe = TestClient(app)

    @app.get(path, include_in_schema=False)
    def whoami(current_user: User = Depends(get_current_user)):
        return {"id": current_user.id, "email": current_user.email}

    return probe


@pytest.fixture()
def registered_user():
    email = _unique_email()
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse-1"},
    )
    assert response.status_code == 201, response.text
    yield email
    _delete_user(email)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_success():
    email = _unique_email()
    try:
        response = client.post(
            "/auth/register",
            json={"email": email, "password": "correct-horse-1"},
        )
        assert response.status_code == 201, response.text

        body = response.json()
        assert body["email"] == email
        assert body["is_active"] is True
        # The password hash must never appear in a response.
        assert "hashed_password" not in body
        assert "password" not in body

        with SessionLocal() as session:
            user = session.execute(
                select(User).where(User.email == email)
            ).scalar_one()
            assert user.hashed_password != "correct-horse-1"
            assert user.hashed_password.startswith("$2")
    finally:
        _delete_user(email)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_success(registered_user):
    response = client.post(
        "/auth/login",
        json={"email": registered_user.upper(), "password": "correct-horse-1"},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["token_type"] == "bearer"
    payload = pyjwt.decode(body["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    assert isinstance(payload["sub"], str)

    with SessionLocal() as session:
        user = session.execute(
            select(User).where(User.email == registered_user)
        ).scalar_one()
        assert str(user.id) == payload["sub"]


def test_login_incorrect_password(registered_user):
    response = client.post(
        "/auth/login",
        json={"email": registered_user, "password": "wrong-password-9"},
    )
    assert response.status_code == 401, response.text


def test_login_unknown_email_is_generic():
    response = client.post(
        "/auth/login",
        json={
            "email": f"ghost-{uuid.uuid4().hex[:8]}@rasikh.test",
            "password": "whatever-1",
        },
    )
    assert response.status_code == 401, response.text
    # Same message as incorrect password — no account enumeration.
    assert response.json()["detail"] == "incorrect email or password"


# ---------------------------------------------------------------------------
# Token verification / get_current_user
# ---------------------------------------------------------------------------


def test_get_current_user_with_valid_token(registered_user):
    login = client.post(
        "/auth/login",
        json={"email": registered_user, "password": "correct-horse-1"},
    )
    token = login.json()["access_token"]

    probe = _protected_probe("/_test/whoami-valid")
    response = probe.get(
        "/_test/whoami-valid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == registered_user


def test_expired_token_is_rejected():
    expired = pyjwt.encode({"sub": "1", "exp": 0}, SECRET_KEY, algorithm=ALGORITHM)
    probe = _protected_probe("/_test/whoami-expired")
    response = probe.get(
        "/_test/whoami-expired",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401, response.text


def test_garbage_token_is_rejected():
    probe = _protected_probe("/_test/whoami-garbage")
    response = probe.get(
        "/_test/whoami-garbage",
        headers={"Authorization": "Bearer this.is.not.a.jwt"},
    )
    assert response.status_code == 401, response.text


def test_missing_token_is_unauthorized():
    _protected_probe("/_test/whoami-missing")
    probe = TestClient(app)
    response = probe.get("/_test/whoami-missing")
    assert response.status_code == 401, response.text


def test_register_duplicate_email(registered_user):
    response = client.post(
        "/auth/register",
        json={"email": registered_user, "password": "another-pass-1"},
    )
    assert response.status_code == 409, response.text


def test_register_rejects_short_password():
    response = client.post(
        "/auth/register",
        json={"email": _unique_email(), "password": "short"},
    )
    assert response.status_code == 422, response.text


def test_register_rejects_malformed_email():
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "correct-horse-1"},
    )
    assert response.status_code == 422, response.text
