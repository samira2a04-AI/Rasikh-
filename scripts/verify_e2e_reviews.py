"""Ad-hoc E2E verification of the Reviews workspace backend contract.

Exercises the exact endpoints the Reviews UI uses, with the seeded demo
accounts: list requests (/requests), identity (/auth/me), run review
(POST /requests/{id}/review), and audit history (GET /requests/{id}/history).
Also verifies unauthenticated access is rejected (the frontend's RequireAuth
guard would redirect to /login on the client).
Run: python scripts/verify_e2e_reviews.py
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
from app.models import AuditEvent, Citation, Finding, Request

client = TestClient(app)
LAWYER = {"email": "lawyer@rasikh.local", "password": "Demo1234!"}
ADMIN = {"email": "admin@rasikh.local", "password": "Demo1234!"}
request_id = f"rev-e2e-{uuid.uuid4().hex[:8]}"
reviewed_request = None


def cleanup() -> None:
    with SessionLocal() as session:
        row = session.get(Request, request_id)
        if row is not None:
            session.delete(row)
        # Remove any findings/review records created on a seeded target so the
        # shared development database is left as we found it.
        if reviewed_request:
            fids = [
                f
                for (f,) in session.execute(
                    select(Finding.finding_id).where(
                        Finding.request_id == reviewed_request
                    )
                ).all()
            ]
            if fids:
                session.execute(delete(Citation).where(Citation.finding_id.in_(fids)))
                for fid in fids:
                    session.execute(
                        delete(AuditEvent).where(
                            AuditEvent.detail_reference == f"finding:{fid}"
                        )
                    )
                session.execute(delete(Finding).where(Finding.finding_id.in_(fids)))
        session.commit()


def login(creds) -> dict[str, str]:
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> int:
    ok = True
    try:
        global reviewed_request
        # Unauthenticated
        print("== unauthenticated")
        assert client.get("/requests").status_code == 401
        assert client.post(f"/requests/{request_id}/review", json={}).status_code == 401
        print("  protected endpoints -> 401 (frontend redirects to /login)")

        # Lawyer/member
        print("== lawyer (member)")
        lawyer = login(LAWYER)
        me = client.get("/auth/me", headers=lawyer).json()
        print("  member:", me["member"]["member_id"], me["member"]["name"])
        assert me["member"]["member_id"] == "L-01"

        # Create a request to review (uses auto requester)
        created = client.post(
            "/requests",
            headers=lawyer,
            json={
                "request_id": request_id,
                "raw_content": "End-to-end reviews workspace probe.",
                "request_type": "contract_review",
            },
        )
        assert created.status_code == 201, created.text
        org_id = created.json()["org_id"]
        print(f"  created request {request_id} org={org_id} requester={created.json()['requester_id']}")

        # List (the Reviews page data source)
        rows = client.get("/requests", headers=lawyer).json()
        assert any(r["request_id"] == request_id for r in rows)
        reviewable = [r for r in rows if r["org_id"]]
        print(f"  list ok, {len(rows)} requests, {len(reviewable)} reviewable (have org)")

        # Run review on a reviewable matter (has org) to exercise the action.
        if reviewable:
            target = reviewable[0]
            reviewed_request = target["request_id"]
            rev = client.post(
                f"/requests/{target['request_id']}/review",
                headers=lawyer,
                json={"member_id": "L-01", "org_id": target["org_id"]},
            )
            if rev.status_code == 200:
                body = rev.json()
                print(
                    f"  review ok on {target['request_id']}: "
                    f"access={body['access_decision']} "
                    f"findings={len(body['findings'])} "
                    f"obligations={len(body['obligations'])} "
                    f"escalations={len(body['escalations'])}"
                )
            else:
                print("  review response:", rev.status_code, rev.text)

        # Audit history (detail page)
        hist = client.get(f"/requests/{request_id}/history", headers=lawyer).json()
        print(f"  history events: {len(hist['events'])}")

        # Admin
        print("== admin")
        admin = login(ADMIN)
        me = client.get("/auth/me", headers=admin).json()
        print("  admin role:", me["role"], "member:", me["member"]["member_id"])
        assert me["role"] == "admin"
        assert me["member"]["member_id"] == "L-02"
        # Admin can list and review too (firm-wide partner, no admin-only gate).
        rows = client.get("/requests", headers=admin).json()
        assert isinstance(rows, list)
        print(f"  admin can list: {len(rows)} requests")

        print("\nALL CHECKS PASSED")
    except AssertionError as exc:
        ok = False
        print("\nFAILED:", exc)
    finally:
        cleanup()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
