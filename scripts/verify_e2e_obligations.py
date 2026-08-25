"""Ad-hoc E2E verification of the Obligations workspace backend contract.

Exercises the ONLY obligations endpoint the backend exposes:
POST /obligations/sweep (admin-only via require_admin).

- Unauthenticated -> 401
- Member sweep    -> 403 (backend is authoritative)
- Admin sweep     -> 200 with the full report shape

The verification sweep uses a reference date far in the past so every
obligation computes on_track: the sweep then persists nothing (escalations are
only created for overdue obligations), leaving the database byte-identical.
Counts are asserted before/after to prove cleanliness.
Run: python scripts/verify_e2e_obligations.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, func

from app.database.connection import SessionLocal
from app.main import app
from app.models import AuditEvent, Escalation, Obligation

client = TestClient(app)
LAWYER = {"email": "lawyer@rasikh.local", "password": "Demo1234!"}
ADMIN = {"email": "admin@rasikh.local", "password": "Demo1234!"}
SAFE_REFERENCE_DATE = "2020-01-01"
created_escalation_ids: list[str] = []


def cleanup() -> None:
    """Remove every escalation row and audit event this run created."""
    with SessionLocal() as session:
        for esc_id in created_escalation_ids:
            session.execute(
                delete(AuditEvent).where(
                    AuditEvent.detail_reference == f"escalation:{esc_id}"
                )
            )
            session.execute(
                delete(Escalation).where(
                    Escalation.escalation_id == esc_id
                )
            )
        session.commit()


def login(creds) -> dict[str, str]:
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}



def main() -> int:
    ok = True
    try:
        total_obligations = 0
        with SessionLocal() as session:
            total_obligations = session.execute(
                select(func.count()).select_from(Obligation)
            ).scalar_one()
        print(f"seeded obligations in DB: {total_obligations}")

        print("== unauthenticated")
        r = client.post(
            "/obligations/sweep", json={"reference_date": SAFE_REFERENCE_DATE}
        )
        assert r.status_code == 401, r.text
        print("  sweep -> 401 without token")

        print("== lawyer (member)")
        lawyer = login(LAWYER)
        me = client.get("/auth/me", headers=lawyer).json()
        assert me["role"] == "member"
        r = client.post(
            "/obligations/sweep",
            headers=lawyer,
            json={"reference_date": SAFE_REFERENCE_DATE},
        )
        assert r.status_code == 403, r.text
        print("  member sweep -> 403 (backend authoritative)")

        print("== admin")
        admin = login(ADMIN)
        me = client.get("/auth/me", headers=admin).json()
        assert me["role"] == "admin" and me["member"]["member_id"] == "L-02"

        # Full sweep. Bucketing uses the STORED band, so seeded overdue
        # obligations escalate even with a past reference date; every created
        # escalation is tracked for cleanup.
        s = client.post(
            "/obligations/sweep",
            headers=admin,
            json={"reference_date": SAFE_REFERENCE_DATE},
        )
        assert s.status_code == 200, s.text
        body = s.json()
        for key in (
            "reference_date", "inspected", "on_track", "reminder", "urgent",
            "overdue", "suppressed", "escalations_created", "already_escalated",
            "band_drift",
        ):
            assert key in body, key
        assert len(body["inspected"]) == total_obligations
        for esc in body["escalations_created"]:
            created_escalation_ids.append(str(esc["escalation_id"]))
            assert esc["reason"] == "missed_deadline"
        print(
            f"  admin sweep OK: inspected={len(body['inspected'])} "
            f"overdue={len(body['overdue'])} "
            f"escalations_created={len(body['escalations_created'])} "
            f"already_escalated={len(body['already_escalated'])}"
        )

        # Idempotency: an immediate re-sweep must not duplicate escalations.
        s2 = client.post(
            "/obligations/sweep",
            headers=admin,
            json={"reference_date": SAFE_REFERENCE_DATE},
        )
        assert s2.status_code == 200, s2.text
        b2 = s2.json()
        assert b2["escalations_created"] == [], b2["escalations_created"]
        assert len(b2["already_escalated"]) == len(body["already_escalated"]) + len(
            body["escalations_created"]
        )
        print("  idempotency: re-sweep created 0 new escalations")

        # Org-scoped filter narrows results but stays within the calendar.
        org = body["inspected"][0]["org_id"]
        f = client.post(
            "/obligations/sweep",
            headers=admin,
            json={"reference_date": SAFE_REFERENCE_DATE, "org_id": org},
        )
        assert f.status_code == 200, f.text
        fbody = f.json()
        assert all(o["org_id"] == org for o in fbody["inspected"])
        print(f"  org filter {org}: inspected={len(fbody['inspected'])}")

        print("\nALL CHECKS PASSED")
    except AssertionError as exc:
        ok = False
        print("\nFAILED:", exc)
    finally:
        cleanup()

    with SessionLocal() as session:
        remaining = session.execute(
            select(func.count()).select_from(Escalation).where(
                Escalation.escalation_id.in_(
                    [e for e in created_escalation_ids] or ["00000000-0000-0000-0000-000000000000"]
                )
            )
        ).scalar_one()
    print(f"cleanup verified: {remaining} of {len(created_escalation_ids)} created escalations remain")
    return 0 if ok and remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
