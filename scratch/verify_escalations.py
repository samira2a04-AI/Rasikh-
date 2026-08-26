import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.services.obligation_sweep import sweep_obligations

def test_sweep():
    with SessionLocal() as session:
        ref_date = date(2026, 7, 1)
        res = sweep_obligations(session, reference_date=ref_date)
        session.commit()
        
        print(f"Reference Date: {res.reference_date}")
        print(f"Total Obligations Inspected: {len(res.inspected)}")
        print(f"  On track: {len(res.on_track)}")
        print(f"  Reminder: {len(res.reminder)}")
        print(f"  Urgent: {len(res.urgent)}")
        print(f"  Overdue: {len(res.overdue)}")
        print(f"\nEscalations Created ({len(res.escalations_created)}):")
        for esc in res.escalations_created:
            print(f"  - Escalation {esc.escalation_id} | Obligation: {esc.obligation_id} | Reason: {esc.reason} | Routed: {esc.routed_to_id}")

if __name__ == "__main__":
    test_sweep()
