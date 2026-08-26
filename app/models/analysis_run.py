"""AnalysisRun model — one execution of AI review over a request (Phase 1).

Groups the Findings produced by a single run and carries a deterministic
result summary derived from those findings. ``status`` follows the small
lifecycle: running -> completed | failed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.finding import Finding
    from app.models.request import Request


class AnalysisRun(Base):
    """One analysis execution for a request.

    - ``status``: 'running' | 'completed' | 'failed'.
    - ``summary``: deterministic factual synthesis of the run's findings
      (counts, highest severity, groundedness) — never invented narrative.
    - ``engine``: which evaluator produced the findings ('llm' or
      'deterministic_fallback') so fallback output is never mistaken for
      Gemini output.
    - Count columns are snapshots taken at completion time.
    """

    __tablename__ = "analysis_run"
    __table_args__ = (
        Index("ix_analysis_run_request_id", "request_id"),
    )

    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("request.request_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    finding_count: Mapped[int] = mapped_column(default=0)
    high_severity_count: Mapped[int] = mapped_column(default=0)
    grounded_count: Mapped[int] = mapped_column(default=0)
    ungrounded_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    request: Mapped[Request] = relationship("Request", back_populates="analysis_runs")
    findings: Mapped[list[Finding]] = relationship(
        "Finding", back_populates="analysis_run"
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisRun analysis_run_id={self.analysis_run_id!r} "
            f"request_id={self.request_id!r} status={self.status!r}>"
        )