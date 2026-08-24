"""Escalation model — hard-case routing (litigation, statutory, Sharia, missed deadline)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.obligation import Obligation
    from app.models.request import Request
    from app.models.team_member import TeamMember


class Escalation(Base):
    """An escalation of a request or an obligation to a lawyer or scholar.

    Exactly one of ``request_id`` / ``obligation_id`` must be non-null
    (enforced by CHECK constraint). No drafted legal answer is produced for
    escalated cases (ESC-006) — that gate lives in application code.
    """

    __tablename__ = "escalation"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('litigation', 'statutory_question', 'sharia_ruling', "
            "'missed_deadline')",
            name="ck_escalation_reason",
        ),
        CheckConstraint(
            "(request_id IS NOT NULL AND obligation_id IS NULL) "
            "OR (request_id IS NULL AND obligation_id IS NOT NULL)",
            name="ck_escalation_exactly_one_target",
        ),
    )

    escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        Text,
        ForeignKey("request.request_id"),
        nullable=True,
    )
    obligation_id: Mapped[Optional[str]] = mapped_column(
        Text,
        ForeignKey("obligation.obligation_id"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    routed_to_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("team_member.member_id"),
        nullable=False,
    )
    evidence_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships (as documented in docs/data-schema.md §4)
    request: Mapped[Optional[Request]] = relationship(
        "Request", back_populates="escalations"
    )
    obligation: Mapped[Optional[Obligation]] = relationship(
        "Obligation", back_populates="escalations"
    )
    routed_to: Mapped[TeamMember] = relationship(
        "TeamMember", back_populates="routed_escalations"
    )

    def __repr__(self) -> str:
        return (
            f"<Escalation escalation_id={self.escalation_id!r} "
            f"reason={self.reason!r}>"
        )