"""Ad-hoc end-to-end verification of the demo user journey.

Exercises the actual app against the seeded database with the demo creds:
lawyer login -> create request (auto requester) -> list -> detail -> history;
admin login; invalid creds; unauthenticated 401. Cleans up its test rows.
Run: python scripts/verify_e2e_demo.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Make the repository root importable regardless of where this is run from.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from app.database.connection import SessionLocal
from app.main import app
from app.models import Request

client = TestClient(app)
LAWYER = {"email": "lawyer@rasikh.local", "password": "Demo1234!"}
ADMIN = {"email": "admin@rasikh.local", "password": "Demo1234!"}
request_id = f"e2e-demo-{uuid.uuid4().hex[:8]}"


def cleanup() -> None:
    with SessionLocal() as session:
        row = session.get(Request, request_id)
        if row is not None:
            session.delete(row)
        session.commit()


def step(label: str) -> None:
    print(f"\n== {label}")


def main() -> int:
    ok = True
    try:
        # Invalid credentials
        step("invalid password rejected")
        r = client.post("/auth/login", json={**LAWYER, "password": "wrong"})
        assert r.status_code == 401, r.text
        print("  invalid creds -> 401", r.json()["detail"])

        # Unauthenticated protected
        step("unauthenticated /requests -> 401")
        assert client.get("/requests").status_code == 401
        print("  401 OK")

        # Lawyer login
        step("lawyer login")
        r = client.post("/auth/login", json=LAWYER)
        assert r.status_code == 200, r.text
        lawyer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        print("  login OK")

        # /auth/me
        step("lawyer /auth/me")
        me = client.get("/auth/me", headers=lawyer_headers).json()
        print("  me:", me["email"], "member=", me["member"])
        assert me["member"]["member_id"] == "L-01"

        # Create request WITHOUT requester_id -> backend derives L-01
        step("create request (auto requester)")
        created = client.post(
            "/requests",
            headers=lawyer_headers,
            json={
                "request_id": request_id,
                "raw_content": "E2E demo request for end-to-end verification.",
                "request_type": "consultation",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        print("  created:", body["request_id"], "requester=", body["requester_id"])
        assert body["requester_id"] == "L-01"

        # List
        step("list requests")
        rows = client.get("/requests", headers=lawyer_headers).json()
        assert any(ro["request_id"] == request_id for ro in rows)
        print(f"  list shows {request_id} (total {len(rows)})")

        # Detail
        step("open request")
        detail = client.get(
            f"/requests/{request_id}", headers=lawyer_headers
        ).json()
        print("  detail status:", detail["status"])
        assert detail["request_id"] == request_id

        # History
        step("audit history")
        hist = client.get(
            f"/requests/{request_id}/history", headers=lawyer_headers
        ).json()
        print(f"  history events: {len(hist['events'])}")
        assert hist["request_id"] == request_id

        # Admin login
        step("admin login")
        r = client.post("/auth/login", json=ADMIN)
        assert r.status_code == 200, r.text
        admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = client.get("/auth/me", headers=admin_headers).json()
        print("  me:", me["email"], "role=", me["role"], "member=", me["member"])
        assert me["role"] == "admin"
        assert me["member"]["member_id"] == "L-02"

        print("\nALL CHECKS PASSED")
    except AssertionError as exc:
        ok = False
        print("\nFAILED:", exc)
    finally:
        cleanup()
    return 0 if ok else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
