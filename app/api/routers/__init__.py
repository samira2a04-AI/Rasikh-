"""API routers for the Rasikh Legal Platform."""

from app.api.routers.approvals import router as approvals_router
from app.api.routers.counts import router as counts_router
from app.api.routers.drafts import router as drafts_router
from app.api.routers.history import router as history_router
from app.api.routers.obligations import router as obligations_router
from app.api.routers.requests import router as requests_router
from app.api.routers.review import router as review_router

__all__ = [
    "approvals_router",
    "counts_router",
    "drafts_router",
    "history_router",
    "obligations_router",
    "requests_router",
    "review_router",
]
