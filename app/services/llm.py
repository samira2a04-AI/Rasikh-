import os
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
import numpy as np

# Use the synchronous Google GenAI client
api_key = os.environ.get("GEMINI_API_KEY", "mock-key-for-local-testing")
client = genai.Client(api_key=api_key) if api_key != "mock-key-for-local-testing" else None

class LLMFinding(BaseModel):
    statement: str = Field(..., description="The structured finding statement. If ungrounded, must include 'not addressed in the documents'.")
    risk_rating: str | None = Field(None, description="Risk rating (e.g., 'Low risk', 'Medium risk', 'High risk').")
    sharia_sensitive_flag: bool = Field(False, description="True if the clause contains interest or penalties.")
    cited_contract_clause_ids: list[str] = Field(default_factory=list, description="List of contract_clause UUIDs used as citations.")
    cited_standard_clause_ids: list[str] = Field(default_factory=list, description="List of review_standard_clause UUIDs used as citations.")

class LLMReviewResult(BaseModel):
    findings: list[LLMFinding]

class LLMClassificationResult(BaseModel):
    request_type: str | None = Field(None, description="The classified request type: 'contract_review', 'consultation', 'meeting_prep', or 'obligation_check'.")
    org_id: str | None = Field(None, description="The identified organisation ID (UUID) if a match is found.")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0.")
    needs_clarification: bool = Field(..., description="True if the request is too vague, ambiguous, or if the organisation cannot be confidently identified.")
    reason: str = Field(..., description="Explanation of the classification or why clarification is needed.")

class LLMGeneratedDraft(BaseModel):
    content: str = Field(..., description="A single grounded legal draft/memo. Must reflect ONLY the supplied findings and their cited clauses; it remains subject to lawyer review and approval.")


def get_embedding(text: str) -> list[float]:
    """Fetch the embedding for a given text from Gemini."""
    # For local dev without an API key, we return random embeddings
    if not client:
        return list(np.random.rand(3072).astype(float))
        
    response = client.models.embed_content(
        model="gemini-embedding-2",
        contents=text
    )
    return response.embeddings[0].values

def evaluate_clauses_via_llm(contract_text: str, standard_text: str) -> list[LLMFinding]:
    """Call the LLM to evaluate the contract against the standard."""
    if not client:
        # For mock testing, extract a real clause UUID from the prompt to create a valid citation
        import re
        match = re.search(r"\[Clause ID: ([a-f0-9\-]+)\]", contract_text, re.IGNORECASE)
        cited_c_ids = [match.group(1)] if match else []

        # Return a mock finding
        return [
            LLMFinding(
                statement="Mock finding due to missing GEMINI_API_KEY.",
                risk_rating="Low risk",
                sharia_sensitive_flag=False,
                cited_contract_clause_ids=cited_c_ids,
                cited_standard_clause_ids=[]
            )
        ]
        
    system_prompt = f"""
    You are an expert legal AI assistant reviewing a contract against a firm's review standard.
    
    Firm Review Standard:
    {standard_text}
    
    You must return a structured JSON array of findings.
    For each finding:
    - State the finding clearly.
    - Provide the risk rating.
    - If the finding is based on the contract text, provide the EXACT UUIDs of the contract clauses and standard clauses you are citing.
    - If the contract does NOT address a standard clause, you MUST include the phrase 'not addressed in the documents' in the statement, and provide ZERO citations.
    """
    
    prompt = f"{system_prompt}\n\nPlease review these contract clauses:\n\n{contract_text}"
    
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=LLMReviewResult,
            temperature=0.0
        )
    )
    
    # response.parsed will contain the Pydantic model parsed from the JSON string
    return response.parsed.findings

def deterministic_classify(raw_content: str) -> str | None:
    text = raw_content.lower().strip()
    
    # 1. Meeting preparation intent
    if any(k in text for k in ["meeting", "briefing", "prepare me", "prep for"]):
        return "meeting_prep"
        
    # 2. Obligation check intent
    if any(k in text for k in ["obligation", "due soon", "overdue", "deadline", "threshold"]):
        return "obligation_check"
        
    # 3. Question / Advice / Consultation intent (even if mentioning contract or agreement)
    consultation_triggers = [
        "can you explain",
        "can the client",
        "what are our rights",
        "is the client allowed",
        "what does this",
        "explain the",
        "how does",
        "advise on",
        "can we",
        "what happens if",
        "what is our position",
        "can this contract be",
        "can we terminate",
    ]
    if any(k in text for k in consultation_triggers):
        return "consultation"
        
    if text.startswith(("can ", "what ", "how ", "is ", "why ", "does ")) and not any(k in text for k in ["review", "audit", "identify risky", "check for risks", "find all risky"]):
        return "consultation"
        
    # 4. Document Review / Audit intent
    review_triggers = [
        "review",
        "identify risky",
        "check this agreement",
        "check for compliance",
        "compliance risks",
        "find all risky",
        "audit",
        "identify missing",
        "inspect",
    ]
    if any(k in text for k in review_triggers):
        return "contract_review"
        
    if "contract" in text or "agreement" in text:
        return "contract_review"

    return "consultation" if "?" in text else None


def classify_request_via_llm(raw_content: str, available_orgs: dict[str, str]) -> LLMClassificationResult:
    """Classify a request and extract its organisation context using Gemini."""
    fallback_type = deterministic_classify(raw_content)
    
    if not client:
        return LLMClassificationResult(
            request_type=fallback_type,
            org_id=None,
            confidence=0.9 if fallback_type else 0.0,
            needs_clarification=fallback_type is None,
            reason="Classification using fallback rules (GEMINI_API_KEY omitted or mock)."
        )

    # Format available organisations for the prompt
    orgs_text = "\n".join(f"- {org_id}: {name}" for org_id, name in available_orgs.items())
    
    system_prompt = f"""
    You are an expert legal AI assistant classifying incoming instructions into one of four exact categories based on the user's INTENT:

    1. contract_review:
       - The user asks Rasikh to inspect/review a document itself, audit risks, check compliance issues, find problematic clauses, or review before signing.
       - Examples: "Review the attached agreement for compliance risks", "Identify risky clauses in this contract", "Find all risky termination clauses".

    2. consultation:
       - The user asks a legal question or requests an explanation, advice, or clarification regarding rights, termination options, liabilities, or legal consequences (even if referring to a contract/agreement).
       - Examples: "Can you explain whether the client can terminate this agreement under the current contract?", "What are our rights if the client terminates?", "Explain the termination rights under this contract".

    3. meeting_prep:
       - The user asks to prepare notes, briefings, or summaries for a meeting, call, or negotiation.
       - Example: "Prepare a briefing for my meeting with the client tomorrow."

    4. obligation_check:
       - The user asks about obligations, deadlines, due dates, overdue items, or compliance tracking.
       - Example: "Which obligations for this organization are overdue or due soon?"

    You must also identify the client organisation the request pertains to from the following known organisations (if mentioned in text):
    {orgs_text}

    Rules:
    1. Set request_type to one of: 'contract_review', 'consultation', 'meeting_prep', or 'obligation_check' based on the core intent.
    2. Questions asking "Can the client...", "What are our rights...", "Explain whether..." MUST be classified as 'consultation' even when referencing contracts.
    3. If an organisation from the list above is mentioned or referenced in the text, set org_id to its ID. If no organisation is mentioned, leave org_id as null.
    4. Do NOT set needs_clarification=true solely because the organisation is missing from the text. Set needs_clarification=true ONLY if the instruction is completely uninterpretable.
    5. Return a structured JSON response.
    """
    
    prompt = f"{system_prompt}\n\nPlease classify this request:\n\n{raw_content}"
    
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LLMClassificationResult,
                temperature=0.0
            )
        )
        parsed = response.parsed
        if not parsed.request_type and fallback_type:
            parsed.request_type = fallback_type
        return parsed
    except Exception as exc:
        return LLMClassificationResult(
            request_type=fallback_type,
            org_id=None,
            confidence=0.8 if fallback_type else 0.0,
            needs_clarification=fallback_type is None,
            reason=f"LLM API call failed ({exc}); used classification rules."
        )

def synthesize_draft_via_llm(context_text: str) -> str | None:
    """Draft a single grounded memo from already-completed analysis + reviewed findings.

    ``context_text`` is a deterministic, structured block built by the AI-drafting
    service from the request, the completed AnalysisRun summary, and the
    human-reviewed Findings (with the clause text each finding cites). The model
    is told to write ONLY from that context and never to invent citations.

    Returns the generated draft text, or ``None`` when no model is configured
    (no ``GEMINI_API_KEY``) so the caller falls back to its deterministic
    composer — matching the local-developer convention used by the other LLM
    helpers in this module.
    """
    if not client:
        return None

    system_prompt = (
        "You are an expert legal drafting assistant inside the Rasikh platform.\n"
        "You are given a request together with its COMPLETED automated analysis "
        "summary and its HUMAN-REVIEWED findings (each finding lists the cited "
        "contract/rulebook clause text).\n"
        "Draft a single, well-structured legal memo (grounded response) that "
        "directly answers the request.\n"
        "Rules:\n"
        "- Write ONLY from the supplied context. Cite the exact clauses the "
        "findings already cite. Never invent clauses, citations, or facts.\n"
        "- If a finding states the matter is 'not addressed in the documents', "
        "say so plainly.\n"
        "- End with a line stating the draft is AI-generated and subject to "
        "lawyer review and approval before it can be treated as final.\n"
        "- Return only the draft text; no markdown fences."
    )

    prompt = f"{system_prompt}\n\n=== CONTEXT ===\n{context_text}"

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=LLMGeneratedDraft,
            temperature=0.0,
        ),
    )

    content = response.parsed.content
    if not content or not content.strip():
        return None
    return content
