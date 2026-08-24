"""Pydantic schemas for the counts panel API (FR-034)."""

from __future__ import annotations

from pydantic import BaseModel


class CountsResponse(BaseModel):
    """At-a-glance operational status for the firm."""

    requests_by_status: dict[str, int]
    drafts_by_approval_state: dict[str, int]
    obligations_by_band: dict[str, int]
    items_awaiting_approval: int
