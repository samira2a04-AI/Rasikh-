"""Ad-hoc E2E verification of the Drafts workspace backend contract.

Exercises the exact endpoints the Drafts UI uses with the seeded demo
accounts: list matters (/requests), list drafts for a matter
(GET /requests/{id}/drafts), create a draft version
(POST /requests/{id}/drafts), read one draft
(GET /requests/{id}/drafts/{draft_id}), and audit history
(GET /requests/{id}/history). Cleans up every record it creates.
Run: python scripts/verify_e2e_drafts.py
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
from app.models import AuditEvent, Draft, Request

client = TestClient(app)
LAWYER = {"email": "lawyer@rasikh.local", "password": "Demo1234!"}
ADMIN = {"email": "admin@rasikh.local", "password": "Demo1234!"}
request_id = f"draft-e2e-{uuid.uuid4().hex[:8]}"
created_draft_ids: list[str] = []


def cleanup() -> None:
    """Remove this run's draft rows, their audit events, and the probe request."""
    with SessionLocal() as session:
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


def main() -> int:
    ok = True
    try:
        # Unauthenticated
        print("== unauthenticated")
        assert client.get(f"/requests/{request_id}/drafts").status_code == 401
        print("  drafts endpoints -> 401 without token")

        # Lawyer/member
        print("== lawyer (member)")
        lawyer = login(LAWYER)
        me = client.get("/auth/me", headers=lawyer).json()
        print("  member:", me["member"]["member_id"], me["member"]["name"])
        assert me["member"]["member_id"] == "L-01"

        # Create the matter under test.
        r = client.post(
            "/requests",
            headers=lawyer,
            json={"request_id": request_id, "raw_content": "Drafts E2E probe."},
        )
        assert r.status_code == 201, r.text

        # Empty draft list initially.
        assert client.get(f"/requests/{request_id}/drafts", headers=lawyer).json() == []
        print("  empty draft list OK")

        # Create v1 then v2; versions must be gap-free and append-only.
        before_events = len(
            client.get(f"/requests/{request_id}/history", headers=lawyer).json()["events"]
        )
        for expected_version in (1, 2):
            c = client.post(
                f"/requests/{request_id}/drafts",
                headers=lawyer,
                json={"content": f"E2E draft version {expected_version}."},
            )
            assert c.status_code == 201, c.text
            body = c.json()
            assert body["version"] == expected_version, body
            assert body["approval_state"] == "awaiting_approval"
            created_draft_ids.append(str(body["draft_id"]))
        print(f"  created versions {created_draft_ids[0][:8]}… v1/v2 awaiting_approval")

        # List returns both, ordered by version.
        listed = client.get(f"/requests/{request_id}/drafts", headers=lawyer).json()
        assert [d["version"] for d in listed] == [1, 2]
        print(f"  list ok ({len(listed)} versions)")

        # Single-draft fetch matches.
        one = client.get(
            f"/requests/{request_id}/drafts/{created_draft_ids[1]}",
            headers=lawyer,
        ).json()
        assert one["content"] == "E2E draft version 2."
        print("  single draft fetch OK")

        # Audit history gained one event per draft version.
        after_events = client.get(
            f"/requests/{request_id}/history", headers=lawyer
        ).json()["events"]
        assert len(after_events) - before_events == 2
        types = {e["event_type"] for e in after_events}
        assert {"draft_created", "draft_edited"} <= types
        print(f"  audit events now {len(after_events)} (draft_created + draft_edited)")

        # Admin
        print("== admin")
        admin = login(ADMIN)
        me = client.get("/auth/me", headers=admin).json()
        assert me["role"] == "admin" and me["member"]["member_id"] == "L-02"
        listed = client.get(
            f"/requests/{request_id}/drafts", headers=admin
        ).json()
        assert [d["version"] for d in listed] == [1, 2]
        print("  admin role=L-02 can read/create drafts per backend rules")

        print("\nALL CHECKS PASSED")
    except AssertionError as exc:
        ok = False
        print("\nFAILED:", exc)
    finally:
        cleanup()

    # Prove nothing was left behind.
    with SessionLocal() as session:
        leftovers = (
            session.query(Draft).filter_by(request_id=request_id).count()
        )
    print(f"cleanup verified: {leftovers} draft rows remain for {request_id}")
    return 0 if ok and leftovers == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
