"""AccessDecision model — every access check, authorized or not (SEC-006, Rule 1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.organisation import Organisation
    from app.models.request import Request
    from app.models.team_member import TeamMember


class AccessDecision(Base):
    """A recorded access check for a request.

    ``basis`` always references MatterAssignment / the firm-wide rule — never
    ``Request.raw_content``. Both positive and negative decisions are recorded
    so unauthorized attempts are traceable (SEC-006).
    """

    __tablename__ = "access_decision"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('authorized', 'unauthorized')",
            name="ck_access_decision_outcome",
        ),
        Index("ix_access_decision_request_id", "request_id"),
        Index(
            "ix_access_decision_member_org_decided_at",
            "member_id",
            "org_id",
            "decided_at",
        ),
    )

    access_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("request.request_id"),
        nullable=False,
    )
    member_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("team_member.member_id"),
        nullable=False,
    )
    org_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("organisation.org_id"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    basis: Mapped[str] = mapped_column(Text, nullable=False)

    # N:1 relationships (as documented in docs/data-schema.md §4)
    request: Mapped[Request] = relationship(
        "Request", back_populates="access_decisions"
    )
    member: Mapped[TeamMember] = relationship(
        "TeamMember", back_populates="access_decisions"
    )
    organisation: Mapped[Organisation] = relationship(
        "Organisation"
    )

    def __repr__(self) -> str:
        return (
            f"<AccessDecision outcome={self.outcome!r} "
            f"request_id={self.request_id!r}>"
        )