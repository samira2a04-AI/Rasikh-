"""FastAPI application entry point for the Rasikh Legal Platform."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    approvals_router,
    counts_router,
    drafts_router,
    history_router,
    obligations_router,
    requests_router,
    review_router,
)


app = FastAPI(
    title="Rasikh",
    description="AI-powered legal and governance platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(requests_router)
app.include_router(review_router)
app.include_router(drafts_router)
app.include_router(approvals_router)
app.include_router(obligations_router)
app.include_router(history_router)
app.include_router(counts_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Report that the API process is available."""
    return {"status": "ok"}
