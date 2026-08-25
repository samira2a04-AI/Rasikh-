"""Tests for the global audit feed (GET /audit).

Uses FastAPI TestClient against the real PostgreSQL database with a throwaway
authenticated user. Temporary AuditEvent rows are created directly (the
append-only audit table has no write API) with a unique marker so cleanup is
exact; nothing leaks between runs.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database.connection import SessionLocal
from app.main import app
from app.models import AuditEvent, Request, User

client = TestClient(app)
MARKER = f"audit-test-{uuid.uuid4().hex[:8]}"
created_event_ids: list[str] = []
created_request_id: str | None = None


def _register_login() -> dict[str, str]:
    email = f"audit-{uuid.uuid4().hex[:10]}@rasikh.test"
    assert (
        client.post("/auth/register", json={"email": email, "password": "correct-horse-1"}).status_code
        == 201
    )
    login = client.post("/auth/login", json={"email": email, "password": "correct-horse-1"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _add(event_type: str, request_id: str | None, actor_id: str | None, seq: int) -> AuditEvent:
    with SessionLocal() as session:
        evt = AuditEvent(
            request_id=request_id,
            event_type=event_type,
            actor_id=actor_id,
            detail_reference=f"{MARKER}:{seq}",
            detail_json={"seq": seq},
        )
        session.add(evt)
        session.commit()
        session.refresh(evt)
        created_event_ids.append(str(evt.audit_event_id))
        return evt


def setup_module(module=None) -> None:
    global created_request_id
    with SessionLocal() as session:
        req = Request(
            request_id=f"audit-api-{uuid.uuid4().hex[:8]}",
            requester_id="L-01",
            raw_content="Audit API probe.",
            status="intake",
        )
        session.add(req)
        session.commit()
        created_request_id = req.request_id

    # Ordered inserts: distinct occurred_at may collide on same-clock commits,
    # so ordering assertions rely on the (occurred_at, id) DESC tiebreaker.
    _add("intake", created_request_id, None, 1)
    _add("classified", created_request_id, None, 2)
    _add("draft_created", created_request_id, None, 3)
    _add("escalated", None, None, 4)          # obligation-style NULL request
    _add("approved", created_request_id, "L-02", 5)


def teardown_module(module=None) -> None:
    with SessionLocal() as session:
        if created_event_ids:
            session.execute(
                delete(AuditEvent).where(AuditEvent.audit_event_id.in_(created_event_ids))
            )
        if created_request_id:
            session.execute(
                delete(AuditEvent).where(AuditEvent.request_id == created_request_id)
            )
            row = session.get(Request, created_request_id)
            if row is not None:
                session.delete(row)
        session.commit()


def test_unauthenticated_is_rejected():
    assert client.get("/audit").status_code == 401


def test_authenticated_returns_events_with_schema():
    headers = _register_login()
    r = client.get("/audit", headers=headers)
    assert r.status_code == 200, r.text
    events = r.json()
    assert isinstance(events, list) and len(events) >= 1
    mine = [e for e in events if e["detail_reference"] and e["detail_reference"].startswith(MARKER)]
    assert len(mine) == 5
    required = {
        "audit_event_id", "request_id", "event_type", "actor_id",
        "detail_reference", "detail_json", "occurred_at",
    }
    assert all(required <= set(e) for e in mine)


def test_newest_first_ordering():
    headers = _register_login()
    events = [
        e for e in client.get("/audit", headers=headers).json()
        if e["detail_reference"] and e["detail_reference"].startswith(MARKER)
    ]
    seqs = [e["detail_json"]["seq"] for e in events]
    assert seqs == sorted(seqs, reverse=True)


def test_null_request_id_events_are_included():
    headers = _register_login()
    events = [
        e for e in client.get("/audit", headers=headers).json()
        if e["detail_reference"] and e["detail_reference"].startswith(MARKER)
    ]
    null_req = [e for e in events if e["request_id"] is None]
    assert [e["event_type"] for e in null_req] == ["escalated"]


def test_request_id_filter():
    headers = _register_login()
    events = client.get(
        "/audit", headers=headers, params={"request_id": created_request_id}
    ).json()
    assert {e["event_type"] for e in events} >= {
        "intake", "classified", "draft_created", "approved"
    }
    assert all(e["request_id"] == created_request_id for e in events)


def test_actor_id_filter():
    headers = _register_login()
    events = client.get(
        "/audit", headers=headers, params={"actor_id": "L-02"}
    ).json()
    mine = [e for e in events if e["detail_reference"] and e["detail_reference"].startswith(MARKER)]
    assert len(mine) == 1 and mine[0]["event_type"] == "approved"


def test_event_type_filter():
    headers = _register_login()
    events = client.get(
        "/audit", headers=headers, params={"event_type": "escalated"}
    ).json()
    assert events, "expected at least the NULL-request escalated probe"
    assert all(e["event_type"] == "escalated" for e in events)


def test_limit_and_offset_pagination():
    headers = _register_login()

    def marker_seqs(params) -> list[int]:
        events = [
            e for e in client.get("/audit", headers=headers, params=params).json()
            if e["detail_reference"] and e["detail_reference"].startswith(MARKER)
        ]
        return [e["detail_json"]["seq"] for e in events]

    page1 = marker_seqs({"limit": 2, "offset": 0})
    page2 = marker_seqs({"limit": 2, "offset": 2})
    full = marker_seqs({})
    assert len(page1) == 2 and len(page2) == 2
    assert not set(page1) & set(page2), "offset must move past the first page"
    combined = sorted(full, reverse=True)
    assert combined.index(page1[0]) < combined.index(page2[0])
    # limit is capped and validated by the API contract.
    assert client.get("/audit", headers=headers, params={"limit": 0}).status_code == 422
    assert client.get("/audit", headers=headers, params={"limit": 201}).status_code == 422
    assert client.get("/audit", headers=headers, params={"offset": -1}).status_code == 422

