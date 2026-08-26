import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.models import ReviewStandardClause, Contract, ContractClause

def inspect_standards():
    with SessionLocal() as session:
        scs = session.query(ReviewStandardClause).all()
        print(f"Total ReviewStandardClause in DB: {len(scs)}")
        applicable = [
            sc for sc in scs
            if sc.clause_number.startswith("1.")
            or sc.clause_number.startswith("4.")
            or sc.category in ("review_checklist", "sharia_sensitive")
        ]
        print(f"Substantive applicable standards (Section 1 & 4): {len(applicable)}")
        for sc in applicable:
            print(f"  Standard {sc.clause_number:<6} (ID: {sc.standard_clause_id}) [{sc.category}]: {sc.text[:60]}...")

if __name__ == "__main__":
    inspect_standards()
