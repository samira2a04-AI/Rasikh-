"""Seed development/demo users for local testing.

Idempotent: running it once creates the demo accounts; running it again never
duplicates them and never resets an existing password. Each account is linked
to a valid firm/team member so the backend can derive the requester identity
from the authenticated user (no manual ``L-01`` entry needed).

Credentials (development only — NEVER use in production):
    lawyer@rasikh.local  /  Demo1234!   (role ``member``, maps to L-01)
    admin@rasikh.local   /  Demo1234!   (role ``admin``,  maps to L-02)

The password is read from ``RASIKH_DEMO_PASSWORD`` when set, otherwise the
dev-only default above is used. Passwords are stored via the project's existing
``hash_password`` (bcrypt) — never in plaintext.

Run from the repository root:
    python scripts/seed_demo_users.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the repository root importable regardless of where this is run from.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select

from app.core.security import hash_password
from app.database.connection import SessionLocal
from app.models import TeamMember, User

# Development-only default. Override via RASIKH_DEMO_PASSWORD for any other env.
DEFAULT_DEMO_PASSWORD = os.getenv("RASIKH_DEMO_PASSWORD", "Demo1234!")

# Email, platform role, and the firm/team member they map to.
# ``role`` uses the project's valid User roles ('member' | 'admin').
DEMO_USERS: list[dict[str, str]] = [
    {
        "display": "Demo Lawyer",
        "email": "lawyer@rasikh.local",
        "role": "member",
        "member_id": "L-01",
    },
    {
        "display": "Demo Admin",
        "email": "admin@rasikh.local",
        "role": "admin",
        "member_id": "L-02",
    },
]


def seed_demo_users(session: SessionLocal) -> dict[str, int]:
    """Create/update the demo users. Returns counts of created/updated rows.

    Idempotent guarantees:
    - Lookup is by email (the unique key on ``users``).
    - An existing account's password is NEVER overwritten.
    - Role and member mapping are synced so re-running repairs drift.
    - The target team member must exist; unknown member_ids are recorded and
      skipped (never synthesised).
    """
    stats = {"created": 0, "updated": 0, "skipped_missing_member": 0}
    hashed = hash_password(DEFAULT_DEMO_PASSWORD)

    for spec in DEMO_USERS:
        email = spec["email"]
        member_id = spec["member_id"]

        member = session.get(TeamMember, member_id)
        if member is None:
            stats["skipped_missing_member"] += 1
            print(f"  skip {email}: team member {member_id!r} not in roster")
            continue

        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user is None:
            session.add(
                User(
                    email=email,
                    hashed_password=hashed,
                    role=spec["role"],
                    member_id=member_id,
                )
            )
            stats["created"] += 1
            print(f"  create {email} ({spec['display']}) -> {member_id}")
        else:
            changed = False
            if user.role != spec["role"]:
                user.role = spec["role"]
                changed = True
            if user.member_id != member_id:
                user.member_id = member_id
                changed = True
            if changed:
                stats["updated"] += 1
                print(f"  update {email}: role/member synced")

    # Make pending inserts visible to later queries in the same transaction so
    # repeated calls in one session are also idempotent (autoflush is False).
    session.flush()
    return stats


def main() -> int:
    print("Seeding demo development users...")
    with SessionLocal() as session, session.begin():
        stats = seed_demo_users(session)
    print("\nResult:")
    print(f"  created: {stats['created']}")
    print(f"  updated (role/member sync): {stats['updated']}")
    print(f"  skipped (missing team member): {stats['skipped_missing_member']}")
    print("\nDemo credentials (development only):")
    print("  lawyer@rasikh.local  /  Demo1234!   (member, maps to L-01)")
    print("  admin@rasikh.local   /  Demo1234!   (admin,  maps to L-02)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
