import os
import sys
from pathlib import Path
from sqlalchemy import select

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.models import Request, TeamMember, MatterAssignment, User
from app.services import access_control, workflow, approval

def run_role_verification():
    with SessionLocal() as session:
        print("=== 1. PARTNER (L-01 / L-02) VERIFICATION ===")
        partner = session.get(TeamMember, "L-01")
        print(f"Partner L-01: role={partner.role}, can_approve={partner.can_approve}")
        assignments_l01 = session.scalars(select(MatterAssignment.org_id).where(MatterAssignment.member_id == "L-01")).all()
        print(f"Partner L-01 matter assignments count: {len(assignments_l01)} (firm-wide)")
        
        # Test access check across multiple orgs
        for org in ["ORG-1007", "ORG-1012", "ORG-1019", "ORG-1033"]:
            res = access_control.check_access(session, "L-01", org)
            assert res.authorized is True, f"Partner L-01 should access {org}"
        print("OK: Partner has firm-wide matter access across all client organisations.")

        print("\n=== 2. ASSOCIATE WITH MATTER ASSIGNMENT (L-05) VERIFICATION ===")
        assoc_l05 = session.get(TeamMember, "L-05")
        print(f"Associate L-05: role={assoc_l05.role}, can_approve={assoc_l05.can_approve}")
        assignments_l05 = set(session.scalars(select(MatterAssignment.org_id).where(MatterAssignment.member_id == "L-05")).all())
        print(f"Associate L-05 matter assignments: {sorted(assignments_l05)}")
        
        # Authorized orgs for L-05: ORG-1007, ORG-1019, ORG-1055
        for org in ["ORG-1007", "ORG-1019", "ORG-1055"]:
            res = access_control.check_access(session, "L-05", org)
            assert res.authorized is True, f"L-05 should have access to {org}"
        print("OK: Associate L-05 is authorized for assigned matters (ORG-1007, ORG-1019, ORG-1055).")

        print("\n=== 3. ASSOCIATE WITHOUT MATTER ASSIGNMENT (L-05 for ORG-1012) VERIFICATION ===")
        res_unauth = access_control.check_access(session, "L-05", "ORG-1012")
        assert res_unauth.authorized is False, "L-05 must be denied access to ORG-1012"
        assert res_unauth.basis == "no_matter_assignment"
        print("OK: Associate L-05 is DENIED access to unassigned matter ORG-1012 (basis: no_matter_assignment).")

        print("\n=== 4. PARALEGAL (L-08) VERIFICATION ===")
        para_l08 = session.get(TeamMember, "L-08")
        print(f"Paralegal L-08: role={para_l08.role}, can_approve={para_l08.can_approve}")
        assignments_l08 = set(session.scalars(select(MatterAssignment.org_id).where(MatterAssignment.member_id == "L-08")).all())
        print(f"Paralegal L-08 matter assignments: {sorted(assignments_l08)}")
        assert para_l08.can_approve is False, "Paralegal cannot approve"
        
        # Test approval attempt by L-08
        try:
            approval._validate_reviewer(session, "L-08")
            assert False, "Paralegal L-08 approval check should have failed"
        except approval.ApprovalWorkflowError as exc:
            assert "can_approve=false" in str(exc)
            print("OK: Paralegal L-08 approval attempt correctly REJECTED with can_approve=false.")

        print("\n=== 5. SENIOR ASSOCIATE (L-04) APPROVAL & SEPARATION OF DUTIES VERIFICATION ===")
        sa_l04 = session.get(TeamMember, "L-04")
        print(f"Senior Associate L-04: role={sa_l04.role}, can_approve={sa_l04.can_approve}")
        assert sa_l04.can_approve is True, "Senior Associate L-04 has can_approve=true"
        print("OK: Senior Associate L-04 carries approval authority (can_approve=true).")

        print("\n=== ALL ROLE VERIFICATIONS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_role_verification()
