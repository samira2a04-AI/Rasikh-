"""MatterAssignment model — who may access which organisation.

The sole authoritative source for access decisions (SEC-001, Rule 2); never
derived from request text.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.organisation import Organisation
    from app.models.team_member import TeamMember


class MatterAssignment(Base):
    """Assignment of a firm member to a client organisation.

    ``UNIQUE (member_id, org_id)`` prevents duplicate assignments; the unique
    constraint's backing index also serves the documented access-lookup index
    on ``(member_id, org_id)``.
    """

    __tablename__ = "matter_assignment"
    __table_args__ = (
        UniqueConstraint("member_id", "org_id", name="uq_matter_assignment_member_org"),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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

    # N:1 relationships (as documented in docs/data-schema.md §4)
    member: Mapped[TeamMember] = relationship(
        "TeamMember", back_populates="matter_assignments"
    )
    organisation: Mapped[Organisation] = relationship(
        "Organisation", back_populates="matter_assignments"
    )

    def __repr__(self) -> str:
        return (
            f"<MatterAssignment member_id={self.member_id!r} "
            f"org_id={self.org_id!r}>"
        )