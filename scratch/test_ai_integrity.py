import os
import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.services.workflow import run_review
from app.services.ai_drafting import generate_ai_draft

def check_env_and_run():
    key = os.environ.get("GEMINI_API_KEY")
    print(f"GEMINI_API_KEY in env: {bool(key)} (starts with '{key[:6]}...' if key else 'None')")
    
    with SessionLocal() as session:
        print("\n--- Running Analysis for DEMO-REQ-CR-01 (ORG-1007, Contract C-01/C-03) ---")
        result_cr1 = run_review(
            session,
            request_id="DEMO-REQ-CR-01",
            member_id="L-01",
            org_id="ORG-1007",
        )
        session.commit()
        
        print(f"AnalysisRun ID: {result_cr1.analysis_run.analysis_run_id}")
        print(f"Engine recorded in AnalysisRun: {result_cr1.analysis_run.engine}")
        print(f"Contracts retrieved: {[c.contract_id for c in result_cr1.contracts]}")
        print(f"Clauses retrieved: {len(result_cr1.clauses)}")
        print(f"Standard clauses retrieved: {len(result_cr1.standard_clauses)}")
        print(f"Findings generated: {len(result_cr1.findings)}")
        for i, f in enumerate(result_cr1.findings[:5], start=1):
            c_cites = [str(c.citation_id) for c in f.citations]
            print(f"  Finding {i}: {f.statement[:80]}... (grounded={f.grounded}, citations={len(c_cites)})")

        print("\n--- Running Analysis for DEMO-REQ-CR-02 (ORG-1003, Document-less) ---")
        result_cr2 = run_review(
            session,
            request_id="DEMO-REQ-CR-02",
            member_id="L-01",
            org_id="ORG-1003",
        )
        session.commit()
        
        print(f"AnalysisRun ID: {result_cr2.analysis_run.analysis_run_id}")
        print(f"Engine recorded in AnalysisRun: {result_cr2.analysis_run.engine}")
        print(f"Contracts retrieved: {[c.contract_id for c in result_cr2.contracts]}")
        print(f"Findings generated: {len(result_cr2.findings)}")
        for f in result_cr2.findings:
            print(f"  Finding: {f.statement} (grounded={f.grounded})")

        print("\n--- Running AI Draft Generation for DEMO-REQ-CR-01 ---")
        # Mark all findings as reviewed first (required precondition for drafting)
        from app.models import Finding
        findings = session.query(Finding).filter(Finding.request_id == "DEMO-REQ-CR-01").all()
        for f in findings:
            f.status = "reviewed"
        session.commit()
        
        draft = generate_ai_draft(session, request_id="DEMO-REQ-CR-01", created_by="L-01")
        session.commit()
        print(f"Draft ID: {draft.draft_id}")
        print(f"Draft Version: {draft.version}")
        print(f"Approval State: {draft.approval_state}")
        print(f"Draft Content:\n{draft.content[:300]}...")

if __name__ == "__main__":
    check_env_and_run()
