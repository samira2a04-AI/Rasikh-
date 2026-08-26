import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.models import Request, Contract, ContractClause, ReviewStandardClause, Organisation

def clean_text(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")

def inspect_req():
    with SessionLocal() as session:
        req = session.get(Request, "REQ-TEST-44bbd09f")
        if req:
            print("=== REQ-TEST-44bbd09f DETAILS ===")
            print(f"ID: {req.request_id}")
            print(f"Requester: {req.requester_id}")
            print(f"Org: {req.org_id}")
            print(f"Request Type: {req.request_type}")
            print(f"Status: {req.status}")
            print(f"Raw content: {clean_text(req.raw_content)}")
        else:
            print("REQ-TEST-44bbd09f not found by ID. Searching all requests containing 44bbd09f:")
            matches = session.query(Request).filter(Request.request_id.like("%44bbd09f%")).all()
            for m in matches:
                print(f"  Match ID: {m.request_id} | Org: {m.org_id} | Raw: {clean_text(m.raw_content)}")

        print("\n=== ORGANISATIONS WITH CONTRACTS ===")
        orgs_with_contracts = session.query(Contract.org_id).distinct().all()
        for o in orgs_with_contracts:
            org_id = o[0]
            contracts = session.query(Contract).filter(Contract.org_id == org_id).all()
            print(f"Org: {org_id} has {len(contracts)} contracts:")
            for c in contracts:
                print(f"  - {c.contract_id}: {clean_text(c.title)}")

if __name__ == "__main__":
    inspect_req()
