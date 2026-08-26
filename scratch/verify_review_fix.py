import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.services.workflow import run_review
from app.models import Request, MatterAssignment, TeamMember

def clean_text(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")

def verify():
    with SessionLocal() as session:
        # 1. Test REQ-TEST-44bbd09f (ORG-1003 document-less request)
        print("=== TEST 1: REQ-TEST-44bbd09f (ORG-1003 document-less) ===")
        # Ensure partner L-01 is assigned to ORG-1003
        ma = session.query(MatterAssignment).filter(
            MatterAssignment.member_id == "L-01",
            MatterAssignment.org_id == "ORG-1003",
        ).first()
        if not ma:
            session.add(MatterAssignment(member_id="L-01", org_id="ORG-1003"))
            session.flush()

        res1 = run_review(
            session,
            request_id="REQ-TEST-44bbd09f",
            member_id="L-01",
            org_id="ORG-1003",
        )
        print(f"Contracts retrieved: {len(res1.contracts)}")
        print(f"Findings count: {len(res1.findings)}")
        for f in res1.findings:
            print(f"  - Statement: {clean_text(f.statement)}")
            print(f"    Grounded: {f.grounded} | Risk: {f.risk_rating}")

        # Check that NO operational clauses (0.2, 0.3, 0.4, 0.5, 5.2, 5.5) exist in findings
        op_clauses = ["Clause 0.2", "Clause 0.3", "Clause 0.4", "Clause 0.5", "Clause 5.2", "Clause 5.5", "Clause 6.3"]
        found_op = [op for op in op_clauses if any(op in f.statement for f in res1.findings)]
        print(f"Spurious operational clauses found: {found_op} (EXPECTED: [])")

        print("\n=== TEST 2: Contract-linked request (ORG-1007 with C-01) ===")
        ma2 = session.query(MatterAssignment).filter(
            MatterAssignment.member_id == "L-01",
            MatterAssignment.org_id == "ORG-1007",
        ).first()
        if not ma2:
            session.add(MatterAssignment(member_id="L-01", org_id="ORG-1007"))
            session.flush()

        res2 = run_review(
            session,
            request_id="TEST-INTENT-CR",
            member_id="L-01",
            org_id="ORG-1007",
        )
        print(f"Contracts retrieved: {len(res2.contracts)}")
        print(f"Clauses retrieved: {len(res2.clauses)}")
        print(f"Findings count: {len(res2.findings)}")
        for f in res2.findings[:10]:
            print(f"  - Statement: {clean_text(f.statement[:80])}...")
            print(f"    Grounded: {f.grounded} | Citations: {len(f.citations)}")

        found_op2 = [op for op in op_clauses if any(op in f.statement for f in res2.findings)]
        print(f"Spurious operational clauses found in contract review: {found_op2} (EXPECTED: [])")

        session.rollback()

if __name__ == "__main__":
    verify()
