"""ApprovalDecision model — recorded lawyer approve/reject tied to a draft version."""

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
    from app.models.draft import Draft
    from app.models.team_member import TeamMember


class ApprovalDecision(Base):
    """A lawyer's decision on a specific draft version.

    ``draft_version`` records the exact version decided upon; the approval
    gate (matching the current Draft.version, reviewer ``can_approve=True``)
    is enforced in application code — not here.
    """

    __tablename__ = "approval_decision"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_approval_decision_decision",
        ),
        Index("ix_approval_decision_draft_id", "draft_id"),
    )

    approval_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("draft.draft_id"),
        nullable=False,
    )
    reviewer_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("team_member.member_id"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # N:1 relationships (as documented in docs/data-schema.md §4)
    draft: Mapped[Draft] = relationship(
        "Draft", back_populates="approval_decisions"
    )
    reviewer: Mapped[TeamMember] = relationship(
        "TeamMember", back_populates="approval_decisions"
    )

    def __repr__(self) -> str:
        return (
            f"<ApprovalDecision decision={self.decision!r} "
            f"draft_version={self.draft_version!r}>"
        )