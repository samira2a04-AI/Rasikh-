"""Ad-hoc E2E verification of the Approvals workspace backend contract.

Exercises the exact endpoints the Approvals UI uses with the seeded demo
accounts: list matters (/requests), list drafts per matter, create a draft to
decide on, approve/reject it (POST /drafts/{id}/approve|reject), and audit
history. Verifies can_approve authority, terminal states, and stale-version
rules. Cleans up every record it creates.
Run: python scripts/verify_e2e_approvals.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database.connection import SessionLocal
from app.main import app
from app.models import ApprovalDecision, AuditEvent, Draft, Request

client = TestClient(app)
LAWYER = {"email": "lawyer@rasikh.local", "password": "Demo1234!"}
ADMIN = {"email": "admin@rasikh.local", "password": "Demo1234!"}
request_id = f"appr-e2e-{uuid.uuid4().hex[:8]}"
created_draft_ids: list[str] = []
created_decision_ids: list[str] = []


def cleanup() -> None:
    """Remove this run's decisions, drafts, audit events, and probe request."""
    with SessionLocal() as session:
        for decision_id in created_decision_ids:
            session.execute(
                delete(AuditEvent).where(
                    AuditEvent.detail_reference == f"approval_decision:{decision_id}"
                )
            )
            session.execute(
                delete(ApprovalDecision).where(
                    ApprovalDecision.approval_decision_id == decision_id
                )
            )
        for draft_id in created_draft_ids:
            session.execute(
                delete(AuditEvent).where(
                    AuditEvent.detail_reference == f"draft:{draft_id}"
                )
            )
            session.execute(delete(Draft).where(Draft.draft_id == draft_id))
        row = session.get(Request, request_id)
        if row is not None:
            session.delete(row)
        session.commit()


def login(creds) -> dict[str, str]:
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def create_draft(headers, content: str) -> dict:
    c = client.post(
        f"/requests/{request_id}/drafts", headers=headers, json={"content": content}
    )
    assert c.status_code == 201, c.text
    body = c.json()
    created_draft_ids.append(str(body["draft_id"]))
    return body
def main() -> int:
    ok = True
    try:
        print("== unauthenticated")
        assert (
            client.post(
                f"/drafts/{uuid.uuid4()}/approve", json={"reviewer_id": "L-01"}
            ).status_code
            == 401
        )
        print("  approve endpoint -> 401 without token")

        print("== lawyer (member)")
        lawyer = login(LAWYER)
        me = client.get("/auth/me", headers=lawyer).json()
        print(f"  member {me['member']['member_id']} can_approve={me['member']['can_approve']}")
        assert me["member"]["member_id"] == "L-01"
        assert me["member"]["can_approve"] is True

        r = client.post(
            "/requests",
            headers=lawyer,
            json={"request_id": request_id, "raw_content": "Approvals E2E probe."},
        )
        assert r.status_code == 201, r.text
        v1 = create_draft(lawyer, "Approvals E2E v1.")
        v2 = create_draft(lawyer, "Approvals E2E v2.")

        stale = client.post(
            f"/drafts/{v1['draft_id']}/approve",
            headers=lawyer,
            json={"reviewer_id": "L-01"},
        )
        assert stale.status_code == 409, stale.text
        print("  acting on stale version -> 409")

        before = len(
            client.get(f"/requests/{request_id}/history", headers=lawyer).json()["events"]
        )
        ap = client.post(
            f"/drafts/{v2['draft_id']}/approve",
            headers=lawyer,
            json={"reviewer_id": "L-01"},
        )
        assert ap.status_code == 200, ap.text
        body = ap.json()
        created_decision_ids.append(str(body["approval_decision_id"]))
        assert body["decision"] == "approved" and body["draft_version"] == 2
        print(f"  approved v2 by {body['reviewer_id']}")

        again = client.post(
            f"/drafts/{v2['draft_id']}/reject",
            headers=lawyer,
            json={"reviewer_id": "L-01"},
        )
        assert again.status_code == 409, again.text
        print("  second decision on decided draft -> 409")

        listed = client.get(f"/requests/{request_id}/drafts", headers=lawyer).json()
        state = {d["version"]: d["approval_state"] for d in listed}
        assert state[2] == "approved", state
        after = client.get(f"/requests/{request_id}/history", headers=lawyer).json()["events"]
        assert len(after) - before == 1
        evt = [e for e in after if e["event_type"] == "approved"][-1]
        assert evt["actor_id"] == "L-01"
        print(f"  audit event 'approved' recorded by {evt['actor_id']}")

        print("== admin")
        admin = login(ADMIN)
        me = client.get("/auth/me", headers=admin).json()
        assert me["role"] == "admin" and me["member"]["member_id"] == "L-02"
        assert me["member"]["can_approve"] is True
        v3 = create_draft(admin, "Approvals E2E v3.")
        rj = client.post(
            f"/drafts/{v3['draft_id']}/reject",
            headers=admin,
            json={"reviewer_id": "L-02"},
        )
        assert rj.status_code == 200, rj.text
        body = rj.json()
        created_decision_ids.append(str(body["approval_decision_id"]))
        assert body["decision"] == "rejected" and body["draft_version"] == 3
        print(f"  rejected v3 by {body['reviewer_id']}")
        listed = client.get(f"/requests/{request_id}/drafts", headers=admin).json()
        assert {d["version"]: d["approval_state"] for d in listed}[3] == "rejected"

        print("\nALL CHECKS PASSED")
    except AssertionError as exc:
        ok = False
        print("\nFAILED:", exc)
    finally:
        cleanup()

    with SessionLocal() as session:
        leftovers_d = session.query(Draft).filter_by(request_id=request_id).count()
    print(f"cleanup verified: {leftovers_d} draft rows remain for {request_id}")
    return 0 if ok and leftovers_d == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
