"""Draft model — AI-produced content awaiting lawyer action (APR-001–APR-005)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.approval_decision import ApprovalDecision
    from app.models.request import Request


class Draft(Base):
    """A versioned draft produced for a request.

    ``version`` starts at 1 and increments on edit; ``approval_state`` is
    awaiting_approval / approved / edited / rejected. Nothing becomes final
    without an ApprovalDecision matching the current version — that gate is
    enforced in application code (FR-032, Rule 5).
    """

    __tablename__ = "draft"
    __table_args__ = (
        CheckConstraint(
            "approval_state IN ('awaiting_approval', 'approved', 'edited', 'rejected')",
            name="ck_draft_approval_state",
        ),
        Index("ix_draft_request_approval_state", "request_id", "approval_state"),
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("request.request_id"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships (as documented in docs/data-schema.md §4)
    request: Mapped[Request] = relationship(
        "Request", back_populates="drafts"
    )
    approval_decisions: Mapped[list[ApprovalDecision]] = relationship(
        "ApprovalDecision", back_populates="draft"
    )

    def __repr__(self) -> str:
        return (
            f"<Draft draft_id={self.draft_id!r} version={self.version!r} "
            f"approval_state={self.approval_state!r}>"
        )