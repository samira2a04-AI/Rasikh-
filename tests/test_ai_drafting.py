"""Tests for the AI-generated drafting feature (completed analysis + reviewed findings).

Covers:
- Service ai_drafting.generate_ai_draft composes a grounded memo from the
  completed AnalysisRun summary and the human-reviewed findings and persists a
  new version through drafting.create_draft in awaiting_approval.
- Preconditions: unknown request -> 404; no completed analysis -> 409; any
  open (unreviewed) finding -> 409 (human review is not bypassed).
- API POST /requests/{request_id}/drafts/generate returns a DraftResponse.

Created rows are removed; nothing leaks, the seeded dataset stays intact.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.security import create_access_token, hash_password
from app.database.connection import SessionLocal
from app.main import app
from app.models import (
    AnalysisRun,
    AuditEvent,
    Citation,
    ContractClause,
    Draft,
    Finding,
    Request,
    User,
)
from app.services import ai_drafting, analysis_run
from app.services.ai_drafting import AIDraftingError
from app.services.review import (
    create_grounded_finding,
    create_ungrounded_finding,
    review_finding,
)

ORG = "ORG-1007"
MEMBER = "L-02"


class _AuthClient(TestClient):
    def __init__(self, token):
        super().__init__(app)
        self._auth_headers = {"Authorization": f"Bearer {token}"}

    def request(self, *args, **kwargs):
        headers = kwargs.pop("headers", None) or {}
        return super().request(*args, headers={**self._auth_headers, **headers}, **kwargs)


def _auth_client_for_member(member_id):
    email = f"aidraft-{member_id.lower()}@rasikh.test"
    with SessionLocal() as session:
        user = session.scalars(select(User).where(User.member_id == member_id)).first()
        if user is None:
            user = User(email=email, hashed_password=hash_password("password-1"),
                        role="member", member_id=member_id)
            session.add(user)
            session.commit()
            session.refresh(user)
        token = create_access_token(str(user.id))
    return _AuthClient(token)


def _clause():
    with SessionLocal() as session:
        clause = session.scalars(
            select(ContractClause).where(ContractClause.contract_id == "C-01")
        ).first()
        assert clause is not None, "seed missing: contract clause C-01"
        session.expunge(clause)
        return clause


def _cleanup(request_id):
    with SessionLocal() as session:
        if session.get(Request, request_id) is None:
            return
        draft_ids = session.scalars(
            select(Draft.draft_id).where(Draft.request_id == request_id)).all()
        finding_ids = session.scalars(
            select(Finding.finding_id).where(Finding.request_id == request_id)).all()
        if draft_ids:
            session.execute(delete(AuditEvent).where(
                AuditEvent.detail_reference.in_([f"draft:{d}" for d in draft_ids])))
            session.execute(delete(Draft).where(Draft.request_id == request_id))
        if finding_ids:
            session.execute(delete(Citation).where(Citation.finding_id.in_(finding_ids)))
            session.execute(delete(Finding).where(Finding.request_id == request_id))
        session.execute(delete(AnalysisRun).where(AnalysisRun.request_id == request_id))
        session.execute(delete(AuditEvent).where(AuditEvent.request_id == request_id))
        session.delete(session.get(Request, request_id))
        session.commit()


def _seed_request(request_id, with_run=True):
    with SessionLocal() as session:
        session.add(Request(
            request_id=request_id, requester_id=MEMBER, org_id=ORG,
            request_type="contract_review",
            raw_content="Draft a response to the client's contract question.",
            status="drafted"))
        if with_run:
            run = analysis_run.start_run(session, request_id=request_id)
            create_grounded_finding(
                session, request_id=request_id,
                statement="The supply term is auto-renewing unless the party gives sixty days' notice.",
                citations=[_clause()], analysis_run_id=run.analysis_run_id)
            session.flush()
            finding = session.scalars(
                select(Finding).where(Finding.request_id == request_id)).first()
            analysis_run.complete_run(session, run=run, findings=[finding], engine="llm")
        session.commit()


def _append_open_finding(request_id):
    with SessionLocal() as session:
        create_ungrounded_finding(
            session, request_id=request_id,
            statement="This is not addressed in the documents provided.")
        session.commit()


def _review_all_findings(request_id):
    with SessionLocal() as session:
        findings = session.scalars(
            select(Finding).where(Finding.request_id == request_id)).all()
        for f in findings:
            review_finding(session, request_id=request_id,
                           finding_id=f.finding_id, reviewer_id=MEMBER)
        session.commit()


def _draft_count():
    with SessionLocal() as session:
        return session.query(Draft).count()


def test_generate_ai_draft_persists_awaiting_approval_version():
    request_id = f"AI-DRAFT-{uuid.uuid4().hex[:8]}"
    baseline = _draft_count()
    try:
        _seed_request(request_id)
        _review_all_findings(request_id)
        with SessionLocal() as session:
            draft = ai_drafting.generate_ai_draft(
                session, request_id=request_id, created_by=MEMBER)
            assert draft.version == 1
            assert draft.approval_state == "awaiting_approval"
            assert draft.created_by == MEMBER
            assert draft.content and draft.content.strip()
            assert "contract" in draft.content.lower()
            session.commit()
        assert _draft_count() == baseline + 1
        with SessionLocal() as session:
            events = session.scalars(select(AuditEvent).where(
                AuditEvent.event_type == "draft_created",
                AuditEvent.request_id == request_id)).all()
            assert len(events) >= 1
            assert events[0].detail_json == {"version": 1}
    finally:
        _cleanup(request_id)


def test_generate_ai_draft_requires_completed_analysis():
    request_id = f"AI-DRAFT-{uuid.uuid4().hex[:8]}"
    try:
        _seed_request(request_id, with_run=False)
        _append_open_finding(request_id)
        with SessionLocal() as session:
            try:
                ai_drafting.generate_ai_draft(
                    session, request_id=request_id, created_by=MEMBER)
                assert False, "expected AIDraftingError"
            except AIDraftingError as exc:
                assert "no completed analysis" in str(exc)
    finally:
        _cleanup(request_id)


def test_generate_ai_draft_blocks_unreviewed_findings():
    request_id = f"AI-DRAFT-{uuid.uuid4().hex[:8]}"
    try:
        _seed_request(request_id)
        _append_open_finding(request_id)
        with SessionLocal() as session:
            try:
                ai_drafting.generate_ai_draft(
                    session, request_id=request_id, created_by=MEMBER)
                assert False
            except AIDraftingError as exc:
                assert "still open" in str(exc)
    finally:
        _cleanup(request_id)


def test_generate_ai_draft_unknown_request_errors():
    request_id = f"AI-DRAFT-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as session:
        try:
            ai_drafting.generate_ai_draft(
                session, request_id=request_id, created_by=MEMBER)
            assert False
        except AIDraftingError as exc:
            assert "unknown request_id" in str(exc)


def test_api_generate_ai_draft_creates_draft():
    request_id = f"AI-DRAFT-{uuid.uuid4().hex[:8]}"
    client = _auth_client_for_member(MEMBER)
    try:
        _seed_request(request_id)
        _review_all_findings(request_id)
        resp = client.post(f"/requests/{request_id}/drafts/generate")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["request_id"] == request_id
        assert body["version"] == 1
        assert body["approval_state"] == "awaiting_approval"
        assert body["created_by"] == MEMBER
        assert body["content"] and body["content"].strip()
        listed = client.get(f"/requests/{request_id}/drafts").json()
        assert any(d["draft_id"] == body["draft_id"] for d in listed)
    finally:
        _cleanup(request_id)


def test_api_generate_ai_draft_409_when_findings_unreviewed():
    request_id = f"AI-DRAFT-{uuid.uuid4().hex[:8]}"
    client = _auth_client_for_member(MEMBER)
    try:
        _seed_request(request_id)
        _append_open_finding(request_id)
        resp = client.post(f"/requests/{request_id}/drafts/generate")
        assert resp.status_code == 409, resp.text
        assert "still open" in resp.json()["detail"]
    finally:
        _cleanup(request_id)


def test_api_generate_ai_draft_404_unknown_request():
    request_id = f"AI-DRAFT-{uuid.uuid4().hex[:8]}"
    client = _auth_client_for_member(MEMBER)
    resp = client.post(f"/requests/{request_id}/drafts/generate")
    assert resp.status_code == 404, resp.text