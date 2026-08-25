"""Ad-hoc E2E verification of the global History workspace contract.

Drives the real workflow (request -> review -> draft -> draft edit -> approval,
plus an admin obligation sweep) against the seeded demo accounts, then proves
GET /audit surfaces every resulting event type — including obligation
escalations whose request_id is NULL. Cleans up every record it creates.
Run: python scripts/verify_e2e_history.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database.connection import SessionLocal
from app.main import app
from app.models import (
    AccessDecision,
    ApprovalDecision,
    AuditEvent,
    Citation,
    Draft,
    Escalation,
    Finding,
    Request,
)

client = TestClient(app)
LAWYER = {"email": "lawyer@rasikh.local", "password": "Demo1234!"}
ADMIN = {"email": "admin@rasikh.local", "password": "Demo1234!"}
REQUEST_ID = f"hist-e2e-{uuid.uuid4().hex[:8]}"
ORG_ID = "ORG-1007"
draft_ids: list[str] = []
decision_ids: list[str] = []
preexisting_escalation_ids: set[str] = set()


def cleanup() -> None:
    """Remove every record this run created, audit events included."""
    with SessionLocal() as session:
        # Any escalation that did not exist before this run is ours.
        ours = [
            e.escalation_id
            for e in session.execute(select(Escalation)).scalars().all()
            if str(e.escalation_id) not in preexisting_escalation_ids
        ]
        for esc_id in ours:
            session.execute(
                delete(AuditEvent).where(
                    AuditEvent.detail_reference == f"escalation:{esc_id}"
                )
            )
            session.execute(delete(Escalation).where(Escalation.escalation_id == esc_id))
        for dec_id in decision_ids:
            session.execute(
                delete(AuditEvent).where(
                    AuditEvent.detail_reference == f"approval_decision:{dec_id}"
                )
            )
            session.execute(
                delete(ApprovalDecision).where(
                    ApprovalDecision.approval_decision_id == dec_id
                )
            )
        findings = session.scalars(
            select(Finding).where(Finding.request_id == REQUEST_ID)
        ).all()
        for f in findings:
            session.execute(delete(Citation).where(Citation.finding_id == f.finding_id))
            session.execute(
                delete(AuditEvent).where(
                    AuditEvent.detail_reference == f"finding:{f.finding_id}"
                )
            )
            session.delete(f)
        for d in draft_ids:
            session.execute(
                delete(AuditEvent).where(AuditEvent.detail_reference == f"draft:{d}")
            )
            session.execute(delete(Draft).where(Draft.draft_id == d))
        # Access decisions recorded during the review must go before the
        # request row (their FK is NOT NULL and has no cascade).
        session.execute(
            delete(AccessDecision).where(AccessDecision.request_id == REQUEST_ID)
        )
        session.execute(delete(AuditEvent).where(AuditEvent.request_id == REQUEST_ID))
        row = session.get(Request, REQUEST_ID)
        if row is not None:
            session.delete(row)
        session.commit()


def login(creds) -> dict[str, str]:
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
def main() -> int:
    ok = True
    try:
        print("== unauthenticated")
        assert client.get("/audit").status_code == 401
        print("  /audit -> 401 without token")

        print("== lawyer drives the full workflow")
        headers = login(LAWYER)
        me = client.get("/auth/me", headers=headers).json()
        assert me["role"] == "member" and me["member"]["member_id"] == "L-01"

        r = client.post(
            "/requests",
            headers=headers,
            json={
                "request_id": REQUEST_ID,
                "raw_content": "History E2E probe for the global audit feed.",
                "request_type": "contract_review",
                "org_id": ORG_ID,
            },
        )
        assert r.status_code == 201, r.text

        rv = client.post(
            f"/requests/{REQUEST_ID}/review",
            headers=headers,
            json={"member_id": "L-01", "org_id": ORG_ID},
        )
        print(f"  review status: {rv.status_code}")
        d1 = client.post(
            f"/requests/{REQUEST_ID}/drafts",
            headers=headers,
            json={"content": "History E2E draft v1."},
        )
        assert d1.status_code == 201, d1.text
        draft_ids.append(str(d1.json()["draft_id"]))
        d2 = client.post(
            f"/requests/{REQUEST_ID}/drafts",
            headers=headers,
            json={"content": "History E2E draft v2."},
        )
        assert d2.status_code == 201, d2.text
        v2 = d2.json()
        draft_ids.append(str(v2["draft_id"]))
        ap = client.post(
            f"/drafts/{v2['draft_id']}/approve",
            headers=headers,
            json={"reviewer_id": "L-01"},
        )
        assert ap.status_code == 200, ap.text
        decision_ids.append(str(ap.json()["approval_decision_id"]))
        print("  request/review/drafts/approval done")

        print("== admin runs the obligation sweep (NULL-request events)")
        admin = login(ADMIN)
        with SessionLocal() as session:
            for e in session.execute(select(Escalation)).scalars().all():
                preexisting_escalation_ids.add(str(e.escalation_id))
        sw = client.post(
            "/obligations/sweep", headers=admin, json={"reference_date": "2026-07-01"}
        )
        assert sw.status_code == 200, sw.text
        new_escalations = [
            str(e["escalation_id"])
            for e in sw.json()["escalations_created"]
        ]
        print(f"  sweep escalations created: {len(new_escalations)}")

        print("== /audit verification")
        events = client.get("/audit", headers=admin, params={"limit": 200}).json()
        mine = [
            e
            for e in events
            if e["request_id"] == REQUEST_ID
            or e["detail_reference"] in [f"escalation:{i}" for i in new_escalations]
        ]
        types = {e["event_type"] for e in mine}
        expected = {
            "intake",
            "classified",
            "document_retrieved",
            "finding_produced",
            "draft_created",
            "draft_edited",
            "approved",
        }
        if new_escalations:
            expected.add("escalated")
        missing = expected - types
        assert not missing, f"missing event types: {missing}"
        print(f"  event types present: {sorted(types)}")

        null_req = [
            e for e in mine if e["request_id"] is None and e["event_type"] == "escalated"
        ]
        assert len(null_req) == len(new_escalations), (
            "escalation events must appear with NULL request"
        )
        seq = [(e["occurred_at"], str(e["audit_event_id"])) for e in events]
        assert seq == sorted(seq, reverse=True), "must be newest first"

        # Filters against this run's data.
        f = client.get(
            "/audit", headers=admin, params={"request_id": REQUEST_ID}
        ).json()
        assert all(e["request_id"] == REQUEST_ID for e in f)
        f = client.get("/audit", headers=admin, params={"actor_id": "L-01"}).json()
        assert all(e["actor_id"] == "L-01" for e in f)
        print("  filters (request_id / actor_id) OK; ordering newest-first OK")

        print("\nALL CHECKS PASSED")
    except AssertionError as exc:
        ok = False
        print("\nFAILED:", exc)
    finally:
        cleanup()

    with SessionLocal() as session:
        leftovers = session.query(Request).filter_by(request_id=REQUEST_ID).count()
    print(
        f"cleanup verified: probe request remains={leftovers}, "
        f"sweep escalations removed={len(new_escalations)}"
    )
    return 0 if ok and leftovers == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
