import uuid

from app.database.connection import SessionLocal
from app.services import workflow

rid = f"REQ-NOPE-{uuid.uuid4().hex[:6]}"
with SessionLocal() as session:
    try:
        workflow.run_review(
            session, request_id=rid, member_id="L-01", org_id="ORG-1007"
        )
    except Exception as exc:
        print("exc:", type(exc).__name__, exc)
        print("cause:", type(exc.__cause__).__name__, exc.__cause__)
        inner = exc.__cause__
        if inner is not None:
            print("inner cause:", type(inner.__context__).__name__)