import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.services.workflow import run_review

def test_cr1():
    with SessionLocal() as session:
        res = run_review(
            session,
            request_id="DEMO-REQ-CR-01",
            member_id="L-01",
            org_id="ORG-1007",
        )
        print(f"Engine: {res.analysis_run.engine}")
        print(f"Total findings: {len(res.findings)}")
        grounded = [f for f in res.findings if f.grounded]
        not_addressed = [f for f in res.findings if not f.grounded]
        sharia = [f for f in res.findings if f.sharia_sensitive_flag]
        print(f"Grounded: {len(grounded)}")
        print(f"Not addressed: {len(not_addressed)}")
        print(f"Sharia sensitive: {len(sharia)}")
        print("\nAll Findings:")
        for i, f in enumerate(res.findings, start=1):
            print(f"  {i}. [{f.status}] Grounded={f.grounded} Sharia={f.sharia_sensitive_flag} | {f.statement[:85]}")

if __name__ == "__main__":
    test_cr1()
