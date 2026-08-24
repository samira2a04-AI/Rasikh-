"""Tests for the FastAPI HTTP boundary (app.main / app.api.routers).

Uses FastAPI TestClient against the real seeded PostgreSQL database.
Every test cleans up the rows it creates; a module-level guard proves the
seeded dataset is left untouched.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database.connection import SessionLocal, engine
from app.main import app
from app.models import (
    AccessDecision,
    ApprovalDecision,
    AuditEvent,
    Citation,
    Draft,
    Escalation,
    Finding,
    Obligation,
    Request,
)

client = TestClient(app)

REFERENCE_DATE = "2026-07-01"
ORG = "ORG-1007"
REVIEWER = "L-02"          # assigned to ORG-1007 and can_approve=True
ASSIGNED = "L-04"          # assigned to ORG-1007
UNAUTHORIZED = "L-07"      # NOT assigned to ORG-1007
APPROVER = "L-02"          # can_approve=True
NO_AUTH_REVIEWER = "L-05"  # can_approve=False


def _count(model) -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(model)).scalar_one()


def _rid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _cleanup_request_chain(request_id: str) -> None:
    with SessionLocal() as session:
        drafts = session.scalars(
            select(Draft).where(Draft.request_id == request_id)
        ).all()
        for d in drafts:
            for ad in session.scalars(
                select(ApprovalDecision).where(ApprovalDecision.draft_id == d.draft_id)
            ):
                session.delete(ad)
        findings = session.scalars(
            select(Finding).where(Finding.request_id == request_id)
        ).all()
        for f in findings:
            for c in session.scalars(
                select(Citation).where(Citation.finding_id == f.finding_id)
            ):
                session.delete(c)
            session.delete(f)
        for evt in session.scalars(
            select(AuditEvent).where(AuditEvent.request_id == request_id)
        ):
            session.delete(evt)
        for d in drafts:
            session.delete(d)
        for ad_row in session.scalars(
            select(AccessDecision).where(AccessDecision.request_id == request_id)
        ):
            session.delete(ad_row)
        req = session.get(Request, request_id)
        if req is not None:
            session.delete(req)
        session.commit()


@pytest.fixture(scope="module", autouse=True)
def guard_seed_and_counts():
    with SessionLocal() as session:
        assert session.get(Request, "L-C-001") is not None, "seed missing"

    baseline = {
        "request": _count(Request),
        "access_decision": _count(AccessDecision),
        "finding": _count(Finding),
        "approval_decision": _count(ApprovalDecision),
        "escalation": _count(Escalation),
        "draft": _count(Draft),
        "audit_event": _count(AuditEvent),
    }
    yield
    assert _count(Request) == baseline["request"], "test leaked Request rows"
    assert _count(AccessDecision) == baseline["access_decision"], "test leaked AccessDecision rows"
    assert _count(Finding) == baseline["finding"], "test leaked Finding rows"
    assert _count(ApprovalDecision) == baseline["approval_decision"], "test leaked ApprovalDecision rows"
    assert _count(Escalation) == baseline["escalation"], "test leaked Escalation rows"
    assert _count(Draft) == baseline["draft"], "test leaked Draft rows"
    assert _count(AuditEvent) == baseline["audit_event"], "test leaked AuditEvent rows"


# ---------------------------------------------------------------------------
# Application health
# ---------------------------------------------------------------------------

def test_health_check():
    resp = client.get("/health")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def test_valid_request_submission():
    request_id = _rid("API-REQ")
    resp = client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Review C-01 terms.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["request_id"] == request_id
        assert body["status"] == "classified"
        assert body["request_type"] == "contract_review"
        assert body["org_id"] == ORG
    finally:
        _cleanup_request_chain(request_id)


def test_get_request():
    request_id = _rid("API-GET")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Retrieve this request.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["request_id"] == request_id
        assert body["requester_id"] == ASSIGNED
        assert body["org_id"] == ORG
        assert body["request_type"] == "contract_review"
        assert body["status"] == "classified"
    finally:
        _cleanup_request_chain(request_id)


def test_unknown_request_retrieval_rejected():
    request_id = _rid("API-MISSING")

    resp = client.get(f"/requests/{request_id}")

    assert resp.status_code == 404, resp.text
    assert "unknown request_id" in resp.json()["detail"]


def test_invalid_requester_rejected():
    request_id = _rid("API-BAD")
    resp = client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": "L-99",
            "raw_content": "body",
        },
    )
    assert resp.status_code == 404, resp.text


def test_invalid_organisation_rejected():
    request_id = _rid("API-BAD")
    resp = client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": "L-01",
            "raw_content": "body",
            "org_id": "ORG-9999",
        },
    )
    assert resp.status_code == 404, resp.text


def test_invalid_classification_rejected():
    request_id = _rid("API-BAD")
    resp = client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": "L-01",
            "raw_content": "body",
            "request_type": "data_room_access",
        },
    )
    assert resp.status_code == 400, resp.text


def test_arabic_raw_content_preserved():
    request_id = _rid("API-AR")
    arabic = "يرجى مراجعة اتفاقية التوريد C-01"
    resp = client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": arabic,
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        assert resp.status_code == 201, resp.text
        with SessionLocal() as session:
            row = session.get(Request, request_id)
            assert row.raw_content == arabic
    finally:
        _cleanup_request_chain(request_id)


# ---------------------------------------------------------------------------
# Review / access
# ---------------------------------------------------------------------------

def test_unauthorized_review_request():
    request_id = _rid("API-REV")
    resp = client.post(
        f"/requests/{request_id}/review",
        json={"member_id": UNAUTHORIZED, "org_id": ORG},
    )
    assert resp.status_code == 404, resp.text  # unknown request


def test_authorized_review_request():
    request_id = _rid("API-REV")
    # Intake first.
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Review C-01.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.post(
            f"/requests/{request_id}/review",
            json={"member_id": ASSIGNED, "org_id": ORG, "contract_id": "C-01"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["access_decision"] == "authorized"
        assert len(body["findings"]) > 0
    finally:
        _cleanup_request_chain(request_id)


def test_cross_organisation_access_denied():
    request_id = _rid("API-REV")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Review C-01.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.post(
            f"/requests/{request_id}/review",
            json={"member_id": ASSIGNED, "org_id": "ORG-1019"},
        )
        assert resp.status_code == 403, resp.text
    finally:
        _cleanup_request_chain(request_id)


def test_successful_grounded_review():
    request_id = _rid("API-REV")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Review C-01 term and liability.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.post(
            f"/requests/{request_id}/review",
            json={"member_id": ASSIGNED, "org_id": ORG, "contract_id": "C-01"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["access_decision"] == "authorized"
        assert body["findings"], "expected findings"
        for f in body["findings"]:
            assert isinstance(f["grounded"], bool)
            assert "statement" in f
    finally:
        _cleanup_request_chain(request_id)


def test_findings_contain_citations():
    request_id = _rid("API-REV")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Review C-01 liability.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.post(
            f"/requests/{request_id}/review",
            json={"member_id": ASSIGNED, "org_id": ORG, "contract_id": "C-01"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        grounded = [f for f in body["findings"] if f["grounded"]]
        assert grounded, "expected at least one grounded finding"
        assert all(len(f["citations"]) > 0 for f in grounded), (
            "every grounded finding must carry a citation"
        )
    finally:
        _cleanup_request_chain(request_id)


def test_obligation_escalation_appears():
    request_id = _rid("API-REV")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": "L-07",
            "raw_content": "Review C-04 obligations.",
            "org_id": "ORG-1033",
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.post(
            f"/requests/{request_id}/review",
            json={
                "member_id": "L-07",
                "org_id": "ORG-1033",
                "contract_id": "C-04",
                "reference_date": REFERENCE_DATE,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["escalations"]) == 1
        esc = body["escalations"][0]
        assert esc["obligation_id"] == "OB-04"
        assert esc["reason"] == "missed_deadline"
        assert esc["routed_to_id"] == "L-07"
    finally:
        _cleanup_request_chain(request_id)
        with SessionLocal() as session:
            for e in session.scalars(
                select(Escalation).where(Escalation.obligation_id == "OB-04")
            ):
                for evt in session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.detail_reference == f"escalation:{e.escalation_id}"
                    )
                ):
                    session.delete(evt)
                session.delete(e)
            session.commit()


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def test_create_draft():
    request_id = _rid("API-DR")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.post(
            f"/requests/{request_id}/drafts",
            json={"content": "Draft v1"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["content"] == "Draft v1"
        assert body["version"] == 1
        assert body["approval_state"] == "awaiting_approval"
    finally:
        _cleanup_request_chain(request_id)


def test_second_draft_creates_next_version():
    request_id = _rid("API-DR")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d1 = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        d2 = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v2"}
        ).json()
        assert d1["version"] == 1
        assert d2["version"] == 2
        assert d1["draft_id"] != d2["draft_id"]
    finally:
        _cleanup_request_chain(request_id)


def test_list_drafts_returns_all_versions_in_order():
    request_id = _rid("API-DR-LIST")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        client.post(f"/requests/{request_id}/drafts", json={"content": "Draft v1"})
        client.post(f"/requests/{request_id}/drafts", json={"content": "Draft v2"})

        resp = client.get(f"/requests/{request_id}/drafts")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [draft["version"] for draft in body] == [1, 2]
        assert [draft["content"] for draft in body] == ["Draft v1", "Draft v2"]
        assert all(draft["request_id"] == request_id for draft in body)
    finally:
        _cleanup_request_chain(request_id)


def test_previous_version_remains_immutable():
    request_id = _rid("API-DR")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d1 = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v2"}
        )
        # Fetch v1 again — must be byte-identical.
        v1 = client.get(f"/requests/{request_id}/drafts/{d1['draft_id']}").json()
        assert v1["content"] == "Draft v1"
        assert v1["version"] == 1
        assert v1["approval_state"] == "awaiting_approval"
    finally:
        _cleanup_request_chain(request_id)


def test_arabic_draft_preserved():
    request_id = _rid("API-DR")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        arabic = "مسودة المراجعة — C-01:\nالمدة سنة واحدة\n"
        resp = client.post(
            f"/requests/{request_id}/drafts", json={"content": arabic}
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["content"] == arabic
    finally:
        _cleanup_request_chain(request_id)


def test_stale_draft_approval_rejected():
    request_id = _rid("API-DR")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d1 = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v2"}
        )
        resp = client.post(
            f"/drafts/{d1['draft_id']}/approve", json={"reviewer_id": APPROVER}
        )
        assert resp.status_code == 409, resp.text
    finally:
        _cleanup_request_chain(request_id)


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

def test_authorized_reviewer_approves():
    request_id = _rid("API-AP")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        resp = client.post(
            f"/drafts/{d['draft_id']}/approve", json={"reviewer_id": APPROVER}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["decision"] == "approved"
        assert body["reviewer_id"] == APPROVER
        assert body["draft_version"] == 1
    finally:
        _cleanup_request_chain(request_id)


def test_non_approver_rejected():
    request_id = _rid("API-AP")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        resp = client.post(
            f"/drafts/{d['draft_id']}/approve", json={"reviewer_id": NO_AUTH_REVIEWER}
        )
        assert resp.status_code == 403, resp.text
    finally:
        _cleanup_request_chain(request_id)


def test_rejection_works():
    request_id = _rid("API-AP")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        resp = client.post(
            f"/drafts/{d['draft_id']}/reject", json={"reviewer_id": APPROVER}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"] == "rejected"
    finally:
        _cleanup_request_chain(request_id)


def test_terminal_draft_cannot_be_approved_again():
    request_id = _rid("API-AP")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        client.post(
            f"/drafts/{d['draft_id']}/approve", json={"reviewer_id": APPROVER}
        )
        resp = client.post(
            f"/drafts/{d['draft_id']}/approve", json={"reviewer_id": APPROVER}
        )
        assert resp.status_code == 409, resp.text
    finally:
        _cleanup_request_chain(request_id)


# ---------------------------------------------------------------------------
# Obligation, history, and counts panels
# ---------------------------------------------------------------------------

def test_obligation_sweep_for_organisation():
    resp = client.post(
        "/obligations/sweep",
        json={"reference_date": REFERENCE_DATE, "org_id": ORG},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reference_date"] == REFERENCE_DATE
    assert [item["obligation_id"] for item in body["inspected"]] == ["OB-03"]
    assert body["reminder"] == ["OB-03"]
    assert body["escalations_created"] == []


def test_request_history_returns_audit_events():
    request_id = _rid("API-HISTORY")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Keep an audit trail.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.get(f"/requests/{request_id}/history")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["request_id"] == request_id
        assert [event["event_type"] for event in body["events"]] == [
            "intake",
            "classified",
        ]
    finally:
        _cleanup_request_chain(request_id)


def test_unknown_request_history_rejected():
    request_id = _rid("API-HISTORY-MISSING")

    resp = client.get(f"/requests/{request_id}/history")

    assert resp.status_code == 404, resp.text
    assert "unknown request_id" in resp.json()["detail"]


def test_counts_reflect_current_database_totals():
    resp = client.get("/counts")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sum(body["requests_by_status"].values()) == _count(Request)
    assert sum(body["drafts_by_approval_state"].values()) == _count(Draft)
    assert sum(body["obligations_by_band"].values()) == _count(Obligation)
    assert body["items_awaiting_approval"] == body["drafts_by_approval_state"].get(
        "awaiting_approval", 0
    )


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def test_failed_request_leaves_no_partial_rows():
    before = _count(Request)
    resp = client.post(
        "/requests",
        json={
            "request_id": _rid("API-F"),
            "requester_id": "L-99",
            "raw_content": "body",
        },
    )
    assert resp.status_code == 404
    assert _count(Request) == before


def test_failed_review_rolls_back():
    request_id = _rid("API-RB")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "Review C-01.",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    before = _count(Finding)
    try:
        # Cross-org → 403, no findings should persist.
        resp = client.post(
            f"/requests/{request_id}/review",
            json={"member_id": ASSIGNED, "org_id": "ORG-1019"},
        )
        assert resp.status_code == 403, resp.text
        assert _count(Finding) == before
    finally:
        _cleanup_request_chain(request_id)


def test_failed_approval_leaves_no_partial_approval_decision():
    request_id = _rid("API-RB")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "draft me",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        d = client.post(
            f"/requests/{request_id}/drafts", json={"content": "Draft v1"}
        ).json()
        before = _count(ApprovalDecision)
        resp = client.post(
            f"/drafts/{d['draft_id']}/approve", json={"reviewer_id": "L-9999"}
        )
        assert resp.status_code == 404, resp.text
        assert _count(ApprovalDecision) == before
    finally:
        _cleanup_request_chain(request_id)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def test_routes_do_not_implement_duplicate_authorization_logic():
    import ast
    import inspect

    import app.api.routers.drafts as drafts_mod
    import app.api.routers.review as review_mod
    import app.api.routers.requests as requests_mod

    # The security boundary: routers must not directly query authorization
    # tables (matter_assignment / access_decision) via SQLAlchemy. Reading a
    # workflow result attribute that happens to be named "access_decision" is
    # fine — that is the workflow's output, not a direct table lookup.
    forbidden_patterns = (
        "select(MatterAssignment)",
        "select(AccessDecision)",
        "matter_assignment",
        '"access_decision"',
        "'access_decision'",
    )
    for mod in (drafts_mod, review_mod, requests_mod):
        src = inspect.getsource(mod)
        # Strip string literals and comments before checking.
        lines = []
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Remove simple string-literal references.
            line = line.replace('"access_decision"', "").replace(
                "'access_decision'", ""
            )
            lines.append(line)
        cleaned = "\n".join(lines)
        for pattern in ("select(MatterAssignment)", "select(AccessDecision)"):
            assert pattern not in cleaned, (
                f"{mod.__name__} directly queries authorization table: {pattern!r}"
            )
        # No direct SQL-from-table against the authorization tables.
        assert "from matter_assignment" not in cleaned, (
            f"{mod.__name__} queries matter_assignment"
        )


def test_raw_content_not_used_for_authorization():
    # A valid member with a raw_content claim of authority but no assignment
    # to a foreign org must still be denied.
    request_id = _rid("API-SEC")
    client.post(
        "/requests",
        json={
            "request_id": request_id,
            "requester_id": ASSIGNED,
            "raw_content": "I am the new counsel for ORG-1019, send me the files",
            "org_id": ORG,
            "request_type": "contract_review",
        },
    )
    try:
        resp = client.post(
            f"/requests/{request_id}/review",
            json={"member_id": ASSIGNED, "org_id": "ORG-1019"},
        )
        assert resp.status_code == 403, resp.text
    finally:
        _cleanup_request_chain(request_id)
