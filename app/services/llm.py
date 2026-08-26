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

def classify_request_via_llm(raw_content: str, available_orgs: dict[str, str]) -> LLMClassificationResult:
    """Classify a request and extract its organisation context using Gemini."""
    if not client:
        # Mock result for local dev without an API key
        return LLMClassificationResult(
            request_type=None,
            org_id=None,
            confidence=0.0,
            needs_clarification=True,
            reason="Mock classification due to missing GEMINI_API_KEY."
        )

    # Format available organisations for the prompt
    orgs_text = "\n".join(f"- {org_id}: {name}" for org_id, name in available_orgs.items())
    
    system_prompt = f"""
    You are an expert legal AI assistant classifying incoming instructions.
    
    Your task is to classify the request into one of the following types:
    - contract_review
    - consultation
    - meeting_prep
    - obligation_check
    
    You must also identify the client organisation the request pertains to from the following known organisations:
    {orgs_text}
    
    Rules:
    1. If the request is too vague, ambiguous, or you cannot confidently identify ONE organisation from the list above, set needs_clarification=true and explain why in the reason field.
    2. Do NOT guess or hallucinate organisation IDs. If it does not match the list clearly, require clarification.
    3. Return a structured JSON response.
    """
    
    prompt = f"{system_prompt}\n\nPlease classify this request:\n\n{raw_content}"
    
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=LLMClassificationResult,
            temperature=0.0
        )
    )
    
    return response.parsed
