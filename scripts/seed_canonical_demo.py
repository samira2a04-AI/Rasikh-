"""Seed canonical demo scenarios and clean up temporary test noise.

Deterministic & Idempotent script:
- Removes temporary REQ-TEST-* rows created during local testing.
- Ensures 4 canonical demo requests exist with clear descriptions.
- Ensures MatterAssignment entries exist for demo users (L-01 Partner, L-02 Senior Associate).

Run: python scripts/seed_canonical_demo.py
"""

from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import delete, select
from app.database.connection import SessionLocal
from app.models import (
    AccessDecision,
    AnalysisRun,
    ApprovalDecision,
    AuditEvent,
    Citation,
    Contract,
    Draft,
    Escalation,
    Finding,
    MatterAssignment,
    Obligation,
    Organisation,
    Request,
    TeamMember,
)

CANONICAL_DEMO_REQUESTS = [
    {
        "request_id": "DEMO-REQ-CR-01",
        "requester_id": "L-01",
        "org_id": "ORG-1007",
        "request_type": "contract_review",
        "status": "intake",
        "raw_content": (
            "Contract Review — Grounded Findings Demo\n\n"
            "Please review Supply Agreement C-01 for ORG-1007 against our firm review standard. "
            "Identify term, liability caps, payment schedule, termination, governing law, and any Sharia-sensitive terms."
        ),
    },
    {
        "request_id": "DEMO-REQ-CR-02",
        "requester_id": "L-01",
        "org_id": "ORG-1003",
        "request_type": "contract_review",
        "status": "intake",
        "raw_content": (
            "Contract Review — No Source Documents Demo\n\n"
            "Review the contract for ORG-1003 for compliance risks and missing essential clauses."
        ),
    },
    {
        "request_id": "DEMO-REQ-OBL-01",
        "requester_id": "L-01",
        "org_id": "ORG-1007",
        "request_type": "obligation_check",
        "status": "intake",
        "raw_content": (
            "Obligation / Escalation Demo\n\n"
            "Check all contractual and statutory obligations for ORG-1007 and identify overdue or urgent items."
        ),
    },
    {
        "request_id": "DEMO-REQ-CONSULT-01",
        "requester_id": "L-02",
        "org_id": "ORG-1019",
        "request_type": "consultation",
        "status": "intake",
        "raw_content": (
            "Consultation Demo — Rights & Termination\n\n"
            "What are our rights if the client terminates the SaaS agreement under ORG-1019?"
        ),
    },
]

def seed_demo():
    with SessionLocal() as session:
        print("=== 1. CLEANING TEMPORARY TEST REQUESTS & STALE APPROVALS/ESCALATIONS ===")
        test_reqs = session.scalars(select(Request).where(Request.request_id.like("REQ-TEST-%"))).all()
        test_req_ids = [r.request_id for r in test_reqs]
        
        # Clear all approval decisions and escalations to leave a clean ground state
        session.execute(delete(ApprovalDecision))
        session.execute(delete(Escalation))
        
        if test_req_ids:
            # Delete dependent findings, drafts, events, access decisions, analysis runs
            session.execute(delete(Citation).where(Citation.finding_id.in_(
                select(Finding.finding_id).where(Finding.request_id.in_(test_req_ids))
            )))
            session.execute(delete(Finding).where(Finding.request_id.in_(test_req_ids)))
            session.execute(delete(Draft).where(Draft.request_id.in_(test_req_ids)))
            session.execute(delete(AccessDecision).where(AccessDecision.request_id.in_(test_req_ids)))
            session.execute(delete(AnalysisRun).where(AnalysisRun.request_id.in_(test_req_ids)))
            session.execute(delete(AuditEvent).where(AuditEvent.request_id.in_(test_req_ids)))
            session.execute(delete(Request).where(Request.request_id.in_(test_req_ids)))
            print(f"Removed {len(test_req_ids)} temporary test requests.")

        print("\n=== 2. SEEDING CANONICAL DEMO REQUESTS ===")
        for req_data in CANONICAL_DEMO_REQUESTS:
            r_id = req_data["request_id"]
            existing = session.get(Request, r_id)
            if not existing:
                session.add(
                    Request(
                        request_id=r_id,
                        requester_id=req_data["requester_id"],
                        org_id=req_data["org_id"],
                        request_type=req_data["request_type"],
                        status=req_data["status"],
                        raw_content=req_data["raw_content"],
                        created_at=datetime.now(timezone.utc),
                    )
                )
                print(f"Created canonical request {r_id} ({req_data['request_type']})")
            else:
                existing.org_id = req_data["org_id"]
                existing.request_type = req_data["request_type"]
                existing.raw_content = req_data["raw_content"]
                print(f"Updated canonical request {r_id}")

        print("\n=== 3. ENSURING MATTER ASSIGNMENTS FOR DEMO USERS ===")
        demo_members = ["L-01", "L-02", "L-03"]
        demo_orgs = ["ORG-1007", "ORG-1003", "ORG-1019", "ORG-1012", "ORG-1033", "ORG-1041"]
        
        for m_id in demo_members:
            for o_id in demo_orgs:
                ma = session.scalars(
                    select(MatterAssignment).where(
                        MatterAssignment.member_id == m_id,
                        MatterAssignment.org_id == o_id,
                    )
                ).first()
                if not ma:
                    session.add(MatterAssignment(member_id=m_id, org_id=o_id))
        
        session.commit()
        print("\nCanonical demo seeding completed successfully!")

if __name__ == "__main__":
    seed_demo()
