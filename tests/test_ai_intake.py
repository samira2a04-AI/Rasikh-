import pytest
import uuid
from app.database.connection import SessionLocal
from app.models import Request, AuditEvent
from app.services import workflow, llm
from app.services.llm import LLMClassificationResult

ASSIGNED = "L-04"

class MockLLMResponse:
    def __init__(self, result):
        self.parsed = result

def test_auto_intake_successful_classification(monkeypatch):
    """Test automatic classification of a review request and org identification."""
    
    def mock_classify(*args, **kwargs):
        return LLMClassificationResult(
            request_type="contract_review",
            org_id="ORG-1007",
            confidence=0.9,
            needs_clarification=False,
            reason="Clear instruction."
        )
    
    monkeypatch.setattr(llm, "classify_request_via_llm", mock_classify)
    
    request_id = f"AI-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as session:
        workflow.auto_intake_and_classify(
            session,
            request_id=request_id,
            requester_id=ASSIGNED,
            raw_content="Review this for ORG-1007",
            org_id=None
        )
        session.commit()
        
    with SessionLocal() as session:
        req = session.get(Request, request_id)
        assert req.status == "classified"
        assert req.request_type == "contract_review"
        assert req.org_id == "ORG-1007"
        session.delete(req)
        for evt in session.query(AuditEvent).filter_by(request_id=request_id).all():
            session.delete(evt)
        session.commit()

def test_auto_intake_ambiguous_request(monkeypatch):
    """Test ambiguous request requiring clarification."""
    
    def mock_classify(*args, **kwargs):
        return LLMClassificationResult(
            request_type=None,
            org_id=None,
            confidence=0.3,
            needs_clarification=True,
            reason="Too ambiguous."
        )
    
    monkeypatch.setattr(llm, "classify_request_via_llm", mock_classify)
    
    request_id = f"AI-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as session:
        workflow.auto_intake_and_classify(
            session,
            request_id=request_id,
            requester_id=ASSIGNED,
            raw_content="Do something",
            org_id=None
        )
        session.commit()
        
    with SessionLocal() as session:
        req = session.get(Request, request_id)
        assert req.status == "insufficient"
        assert req.request_type is None
        assert req.org_id is None
        session.delete(req)
        
        # Cleanup AuditEvent
        for evt in session.query(AuditEvent).filter_by(request_id=request_id).all():
            session.delete(evt)
        session.commit()

def test_explicit_user_selection_overrides_ai(monkeypatch):
    """Test explicit user-selected request_type overriding classification."""
    
    # Even if LLM says something else (though we shouldn't even call it if user provided both, 
    # but here we test the orchestrator handles it if org_id is provided but request_type is None)
    def mock_classify(*args, **kwargs):
        return LLMClassificationResult(
            request_type="meeting_prep",
            org_id="ORG-1033",  # LLM tries to change org
            confidence=0.9,
            needs_clarification=False,
            reason="Override test."
        )
        
    monkeypatch.setattr(llm, "classify_request_via_llm", mock_classify)
    
    request_id = f"AI-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as session:
        # User provides org_id="ORG-1007" but leaves request_type None
        workflow.auto_intake_and_classify(
            session,
            request_id=request_id,
            requester_id=ASSIGNED,
            raw_content="Prepare meeting",
            org_id="ORG-1007"
        )
        session.commit()
        
    with SessionLocal() as session:
        req = session.get(Request, request_id)
        assert req.status == "classified"
        assert req.request_type == "meeting_prep"
        assert req.org_id == "ORG-1007" # Kept explicit org_id
        session.delete(req)
        
        for evt in session.query(AuditEvent).filter_by(request_id=request_id).all():
            session.delete(evt)
        session.commit()


@pytest.mark.parametrize(
    "text,expected_type",
    [
        (
            "Review the attached distribution agreement for compliance risks before signature.",
            "contract_review",
        ),
        (
            "Can you explain whether the client can terminate this agreement under the current contract?",
            "consultation",
        ),
        (
            "Identify risky clauses in this contract.",
            "contract_review",
        ),
        (
            "What are our rights if the client terminates the agreement?",
            "consultation",
        ),
        (
            "Prepare a briefing for my meeting with the client tomorrow.",
            "meeting_prep",
        ),
        (
            "Which obligations for this organization are overdue or due soon?",
            "obligation_check",
        ),
    ],
)
def test_intent_based_classification_cases(text, expected_type):
    """Verify that request classification prioritises intent over plain keyword presence."""
    result = llm.deterministic_classify(text)
    assert result == expected_type
