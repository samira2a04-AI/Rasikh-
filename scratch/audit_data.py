import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.models import (
    Organisation,
    Contract,
    ContractClause,
    Request,
    ReviewStandardClause,
    Finding,
    Draft,
    ApprovalDecision,
    Obligation,
    Escalation,
    AuditEvent,
)

def clean(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")

def audit():
    with SessionLocal() as session:
        print("=== 1. ENTITY COUNTS ===")
        print(f"Organisations: {session.query(Organisation).count()}")
        print(f"Contracts: {session.query(Contract).count()}")
        print(f"ContractClauses: {session.query(ContractClause).count()}")
        print(f"Requests: {session.query(Request).count()}")
        print(f"ReviewStandardClauses: {session.query(ReviewStandardClause).count()}")
        print(f"Findings: {session.query(Finding).count()}")
        print(f"Drafts: {session.query(Draft).count()}")
        print(f"ApprovalDecisions: {session.query(ApprovalDecision).count()}")
        print(f"Obligations: {session.query(Obligation).count()}")
        print(f"Escalations: {session.query(Escalation).count()}")
        print(f"AuditEvents: {session.query(AuditEvent).count()}")

        print("\n=== 2. REQUEST BREAKDOWN ===")
        reqs = session.query(Request).all()
        canonical = [r for r in reqs if not r.request_id.startswith("REQ-TEST-")]
        test_reqs = [r for r in reqs if r.request_id.startswith("REQ-TEST-")]
        print(f"Canonical requests (L-C-* or named): {len(canonical)}")
        print(f"Temporary test requests (REQ-TEST-*): {len(test_reqs)}")

        print("\nSample canonical requests:")
        for r in canonical[:5]:
            c_count = session.query(Contract).filter(Contract.org_id == r.org_id).count()
            print(f"  - {r.request_id} | Org: {r.org_id} ({c_count} contracts) | Type: {r.request_type} | Status: {r.status}")

        print("\n=== 3. ESCALATIONS IN DB ===")
        escs = session.query(Escalation).all()
        print(f"Total Escalations: {len(escs)}")
        for e in escs:
            print(f"  - Escalation {e.escalation_id} | Obl: {e.obligation_id} | Req: {e.request_id} | Org: {e.org_id} | Reason: {e.reason} | Routed: {e.routed_to_id}")

if __name__ == "__main__":
    audit()
