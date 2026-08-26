"""Safe LLM Connectivity & Health Diagnostic for Rasikh.

Reports Gemini LLM API status, key configuration, connectivity, model latency,
and rate limits WITHOUT printing API keys or modifying demo data.

Run: python scripts/diagnose_llm.py
"""

from __future__ import annotations
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def run_diagnostic() -> dict:
    raw_key = os.environ.get("GEMINI_API_KEY")
    is_key_configured = bool(raw_key and raw_key != "mock-key-for-local-testing")
    
    diagnostic = {
        "provider": "Google Gemini",
        "model": "gemini-3.6-flash",
        "api_key_configured": "YES" if is_key_configured else "NO",
        "request_attempted": "NO",
        "response_received": "NO",
        "status": "NOT_ATTEMPTED",
        "structured_response": "NO",
        "fallback_triggered": "YES" if not is_key_configured else "NO",
        "reason": None,
        "latency_ms": 0.0,
    }
    
    if not is_key_configured:
        diagnostic["reason"] = "GEMINI_API_KEY environment variable is missing or set to mock default."
        return diagnostic

    try:
        from google import genai
        from google.genai import types
        from pydantic import BaseModel, Field

        class PingResult(BaseModel):
            status: str = Field(..., description="Ping response status, e.g., 'ok'.")

        client = genai.Client(api_key=raw_key)
        diagnostic["request_attempted"] = "YES"
        
        start_t = time.perf_counter()
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents="Respond with JSON status ok for connectivity check.",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PingResult,
                temperature=0.0,
            ),
        )
        latency = (time.perf_counter() - start_t) * 1000.0
        
        diagnostic["latency_ms"] = round(latency, 2)
        diagnostic["response_received"] = "YES"
        diagnostic["status"] = "200 OK"
        diagnostic["structured_response"] = "YES" if response.parsed else "NO"
        diagnostic["fallback_triggered"] = "NO"
        diagnostic["reason"] = "LLM API connection successful."
        
    except Exception as exc:
        exc_str = str(exc)
        diagnostic["response_received"] = "NO" if "RESOURCE_EXHAUSTED" in exc_str or "429" in exc_str else "ERROR"
        diagnostic["status"] = "429 RESOURCE_EXHAUSTED" if "RESOURCE_EXHAUSTED" in exc_str or "429" in exc_str else "ERROR"
        diagnostic["fallback_triggered"] = "YES"
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
            diagnostic["reason"] = "Gemini API free tier rate limit exceeded (429 RESOURCE_EXHAUSTED). Platform gracefully uses deterministic fallback."
        else:
            diagnostic["reason"] = f"LLM API Exception: {exc_str[:120]}"

    return diagnostic

def print_diagnostic(d: dict):
    print("=" * 60)
    print("      RASIKH LLM / RAG CONNECTIVITY DIAGNOSTIC REPORT")
    print("=" * 60)
    print(f"Provider:             {d['provider']}")
    print(f"Model:                {d['model']}")
    print(f"API key configured:   {d['api_key_configured']}")
    print(f"Request attempted:    {d['request_attempted']}")
    print(f"Response received:    {d['response_received']}")
    print(f"Status:               {d['status']}")
    print(f"Structured response:  {d['structured_response']}")
    print(f"Fallback triggered:   {d['fallback_triggered']}")
    print(f"Reason:               {d['reason']}")
    print(f"Latency:              {d['latency_ms']} ms")
    print("=" * 60)

if __name__ == "__main__":
    res = run_diagnostic()
    print_diagnostic(res)
