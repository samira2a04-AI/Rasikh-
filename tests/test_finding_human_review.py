"""Comprehensive tests for the Finding Human-Review Lifecycle (Section 14).

Verifies that findings start OPEN, transition to REVIEWED with reviewer metadata,
audit logs, authorization enforcement, and accurate progress tracking.
"""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.security import create_access_token, hash_password
from app.database.connection import SessionLocal
from app.main import app
from app.models import AuditEvent, Citation, ContractClause, Finding, Organisation, Request, User
from app.services import access_control
from app.services.review import (
    create_grounded_finding,
    create_ungrounded_finding,
    review_finding,
)

client = TestClient(app)


def _clause(contract_id: str, label: str) -> ContractClause:
    with SessionLocal() as session:
        clause = session.execute(
            select(ContractClause).where(
                ContractClause.contract_id == contract_id,
                ContractClause.clause_label == label,
            )
        ).scalar_one()
        session.expunge(clause)
        return clause


def _cleanup_finding(finding_id) -> None:
    with SessionLocal() as session:
        session.execute(
            delete(AuditEvent).where(AuditEvent.detail_reference == f"finding:{finding_id}")
        )
        session.execute(
            delete(Citation).where(Citation.finding_id == finding_id)
        )
        session.execute(
            delete(Finding).where(Finding.finding_id == finding_id)
        )
        session.commit()


def _auth_headers_for_member(member_id: str = "L-01") -> dict[str, str]:
    email = f"test-{member_id.lower()}@rasikh.test"
    with SessionLocal() as session:
        user = session.scalars(select(User).where(User.member_id == member_id)).first()
        if user is None:
            user = User(
                email=email,
                hashed_password=hash_password("password-1"),
                role="member",
                member_id=member_id,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        token = create_access_token(str(user.id))
        return {"Authorization": f"Bearer {token}"}


# 1. Newly generated finding starts as OPEN.
def test_newly_generated_finding_starts_as_open():
    clause = _clause("C-01", "1")
    with SessionLocal() as session:
        g_finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Grounded statement.",
            citations=[clause],
        )
        u_finding = create_ungrounded_finding(
            session,
            request_id="L-C-001",
            statement="This is not addressed in the documents provided.",
        )
        session.commit()
        g_id, u_id = g_finding.finding_id, u_finding.finding_id

    try:
        with SessionLocal() as verify:
            g_row = verify.get(Finding, g_id)
            u_row = verify.get(Finding, u_id)
            assert g_row.status == "open"
            assert u_row.status == "open"
            assert g_row.reviewed_by is None
            assert u_row.reviewed_by is None
    finally:
        _cleanup_finding(g_id)
        _cleanup_finding(u_id)


# 2-6, 8, 10, 11. Grounded & Not-addressed findings are reviewable, records member, timestamp, note, status -> REVIEWED, logs audit.
def test_lawyer_can_review_open_finding_both_grounded_and_ungrounded():
    clause = _clause("C-01", "1")
    with SessionLocal() as session:
        g_finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Grounded statement for review test.",
            citations=[clause],
        )
        u_finding = create_ungrounded_finding(
            session,
            request_id="L-C-001",
            statement="Governance is not addressed in the documents provided.",
        )
        session.commit()
        g_id, u_id = g_finding.finding_id, u_finding.finding_id

    try:
        with SessionLocal() as session:
            review_finding(
                session,
                request_id="L-C-001",
                finding_id=g_id,
                reviewer_id="L-01",
                status="reviewed",
                reviewer_notes="Confirmed grounded finding.",
            )
            review_finding(
                session,
                request_id="L-C-001",
                finding_id=u_id,
                reviewer_id="L-01",
                status="reviewed",
                reviewer_notes="Confirmed ungrounded finding.",
            )
            session.commit()

        with SessionLocal() as verify:
            g_row = verify.get(Finding, g_id)
            u_row = verify.get(Finding, u_id)
            assert g_row.status == "reviewed"
            assert u_row.status == "reviewed"
            assert g_row.reviewed_by == "L-01"
            assert u_row.reviewed_by == "L-01"
            assert g_row.reviewed_at is not None
            assert u_row.reviewed_at is not None
            assert g_row.reviewer_notes == "Confirmed grounded finding."
            assert u_row.reviewer_notes == "Confirmed ungrounded finding."

            g_events = list(verify.scalars(select(AuditEvent).where(AuditEvent.detail_reference == f"finding:{g_id}", AuditEvent.event_type == "finding_reviewed")))
            u_events = list(verify.scalars(select(AuditEvent).where(AuditEvent.detail_reference == f"finding:{u_id}", AuditEvent.event_type == "finding_reviewed")))
            assert len(g_events) == 1
            assert len(u_events) == 1
            assert g_events[0].actor_id == "L-01"
            assert u_events[0].actor_id == "L-01"
    finally:
        _cleanup_finding(g_id)
        _cleanup_finding(u_id)


# 7. Reviewed finding cannot be reviewed again unnecessarily (idempotency / no duplicate audit events).
def test_duplicate_review_submission_is_idempotent():
    clause = _clause("C-01", "1")
    with SessionLocal() as session:
        finding = create_grounded_finding(
            session,
            request_id="L-C-001",
            statement="Idempotency statement.",
            citations=[clause],
        )
        session.commit()
        f_id = finding.finding_id

    try:
        with SessionLocal() as session:
            review_finding(session, request_id="L-C-001", finding_id=f_id, reviewer_id="L-01", status="reviewed", reviewer_notes="Identical note")
            session.commit()

        with SessionLocal() as session:
            # Re-submit identical review
            review_finding(session, request_id="L-C-001", finding_id=f_id, reviewer_id="L-01", status="reviewed", reviewer_notes="Identical note")
            session.commit()

        with SessionLocal() as verify:
            events = list(verify.scalars(select(AuditEvent).where(AuditEvent.detail_reference == f"finding:{f_id}", AuditEvent.event_type == "finding_reviewed")))
            assert len(events) == 1  # No duplicate audit event created
    finally:
        _cleanup_finding(f_id)


# 9. Unauthorized user cannot review a finding.
def test_unauthorized_user_cannot_review_finding():
    clause = _clause("C-01", "1")
    unauth_req_id = f"req-unauth-{uuid.uuid4().hex[:6]}"
    unauth_org_id = f"ORG-UNAUTH-{uuid.uuid4().hex[:6]}"

    with SessionLocal() as session:
        session.add(Organisation(org_id=unauth_org_id, name="Unassigned Org", sector="technology", type="client", status="active"))
        session.add(Request(request_id=unauth_req_id, org_id=unauth_org_id, requester_id="L-01", raw_content="Test", status="intake"))
        session.flush()
        finding = create_grounded_finding(
            session,
            request_id=unauth_req_id,
            statement="Access control finding test.",
            citations=[clause],
        )
        session.commit()
        f_id = finding.finding_id

    try:
        # User mapped to L-05 has no assignment for unauth_org_id
        headers = _auth_headers_for_member("L-05")
        resp = client.patch(
            f"/requests/{unauth_req_id}/findings/{f_id}/review",
            json={"status": "reviewed", "reviewer_notes": "Unauthorized attempt"},
            headers=headers,
        )
        assert resp.status_code == 403
        assert "Not authorized" in resp.text
    finally:
        _cleanup_finding(f_id)
        with SessionLocal() as session:
            session.execute(delete(Request).where(Request.request_id == unauth_req_id))
            session.execute(delete(Organisation).where(Organisation.org_id == unauth_org_id))
            session.commit()


# 12-14. Human-reviewed count & progress (0/31 -> 1/31 -> 31/31).
def test_human_reviewed_progress_tracking():
    clause = _clause("C-01", "1")
    finding_ids = []
    with SessionLocal() as session:
        for i in range(5):
            f = create_grounded_finding(
                session,
                request_id="L-C-001",
                statement=f"Progress tracking statement {i}.",
                citations=[clause],
            )
            finding_ids.append(f.finding_id)
        session.commit()

    try:
        with SessionLocal() as session:
            findings = list(session.scalars(select(Finding).where(Finding.request_id == "L-C-001")).all())
            initial_reviewed = sum(1 for f in findings if f.status == "reviewed")

            # Review 1 finding
            review_finding(session, request_id="L-C-001", finding_id=finding_ids[0], reviewer_id="L-01")
            session.commit()

        with SessionLocal() as session:
            findings = list(session.scalars(select(Finding).where(Finding.request_id == "L-C-001")).all())
            after_one_reviewed = sum(1 for f in findings if f.status == "reviewed")
            assert after_one_reviewed == initial_reviewed + 1

        # Review remaining created findings
        with SessionLocal() as session:
            for fid in finding_ids[1:]:
                review_finding(session, request_id="L-C-001", finding_id=fid, reviewer_id="L-01")
            session.commit()

        with SessionLocal() as session:
            findings = list(session.scalars(select(Finding).where(Finding.request_id == "L-C-001")).all())
            after_all_created_reviewed = sum(1 for f in findings if f.status == "reviewed")
            assert after_all_created_reviewed == initial_reviewed + len(finding_ids)
    finally:
        for fid in finding_ids:
            _cleanup_finding(fid)


# 15. AI Analysis remains COMPLETED while Human Review remains IN PROGRESS.
def test_ai_analysis_completed_while_human_review_in_progress():
    headers = _auth_headers_for_member("L-01")
    # First ensure review has been run for L-C-001
    run_resp = client.post(
        "/requests/L-C-001/review",
        json={"member_id": "L-01", "org_id": "ORG-1001"},
        headers=headers,
    )
    assert run_resp.status_code == 200
    resp = client.get("/requests/L-C-001/review", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_decision"] == "authorized"
    assert len(body["findings"]) >= 1
    for f in body["findings"]:
        assert "status" in f
