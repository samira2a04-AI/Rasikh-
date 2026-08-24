"""Obligation model — calendar entries with owner, due date, band (FR-016–FR-018)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.escalation import Escalation
    from app.models.organisation import Organisation
    from app.models.team_member import TeamMember


class Obligation(Base):
    """A matter obligation (``OB-xx``).

    ``band`` (overdue / urgent / reminder / on_track) is a derived convenience
    column recomputed from ``due_date`` plus rulebook thresholds at runtime;
    the rulebook remains the source of truth for thresholds.
    """

    __tablename__ = "obligation"
    __table_args__ = (
        Index("ix_obligation_org_due_date", "org_id", "due_date"),
        Index("ix_obligation_band", "band"),
    )

    obligation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    org_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("organisation.org_id"),
        nullable=False,
    )
    owner_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("team_member.member_id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    band: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships (as documented in docs/data-schema.md §4)
    organisation: Mapped[Organisation] = relationship(
        "Organisation", back_populates="obligations"
    )
    owner: Mapped[TeamMember] = relationship(
        "TeamMember", back_populates="owned_obligations"
    )
    escalations: Mapped[list[Escalation]] = relationship(
        "Escalation", back_populates="obligation"
    )

    def __repr__(self) -> str:
        return (
            f"<Obligation obligation_id={self.obligation_id!r} "
            f"due_date={self.due_date!r} band={self.band!r}>"
        )