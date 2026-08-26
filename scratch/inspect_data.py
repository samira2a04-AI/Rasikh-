import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.models import Request, Contract, ContractClause, ReviewStandardClause, Organisation

def clean_text(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")

def inspect_all():
    with SessionLocal() as session:
        print("=== 1. CONTRACTS & ORGANISATIONS IN DB ===")
        contracts = session.query(Contract).all()
        print(f"Total contracts: {len(contracts)}")
        for c in contracts:
            clauses_count = session.query(ContractClause).filter(ContractClause.contract_id == c.contract_id).count()
            print(f"  Contract: {c.contract_id} | Org: {c.org_id} | Title: {clean_text(c.title)} | Clauses: {clauses_count}")

        print("\n=== 2. REQUEST ORG-1003 OR SIMILAR ===")
        reqs = session.query(Request).filter(Request.org_id == "ORG-1003").all()
        print(f"Requests for ORG-1003 ({len(reqs)} total):")
        for r in reqs:
            print(f"  ID: {r.request_id} | Type: {r.request_type} | Status: {r.status} | Content: {clean_text(r.raw_content[:60])}")

        print("\n=== 3. ALL CONTRACT ORGS vs REQUEST ORGS ===")
        all_reqs = session.query(Request).all()
        print(f"Total requests: {len(all_reqs)}")
        for r in all_reqs:
            c_count = session.query(Contract).filter(Contract.org_id == r.org_id).count()
            print(f"  Req: {r.request_id} | Org: {r.org_id} | Type: {r.request_type} | Contracts for Org: {c_count}")

        print("\n=== 4. ALL REVIEW STANDARD CLAUSES (31 TOTAL) ===")
        scs = session.query(ReviewStandardClause).all()
        print(f"Total review standard clauses: {len(scs)}")
        for sc in scs:
            print(f"  ID: {sc.standard_clause_id} | Num: {sc.clause_number} | Text: {clean_text(sc.text[:70])}...")

if __name__ == "__main__":
    inspect_all()
