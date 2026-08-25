"""TeamMember model — firm members, their role, access scope, and approval capability."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.access_decision import AccessDecision
    from app.models.approval_decision import ApprovalDecision
    from app.models.audit_event import AuditEvent
    from app.models.escalation import Escalation
    from app.models.matter_assignment import MatterAssignment
    from app.models.obligation import Obligation
    from app.models.request import Request
    from app.models.user import User


class TeamMember(Base):
    """A firm member (partner / senior_associate / associate / paralegal).

    Natural primary key ``member_id`` (e.g. ``L-01`` … ``L-10``) is preserved
    from ``firm_team.json``.
    """

    __tablename__ = "team_member"
    __table_args__ = (
        CheckConstraint(
            "role IN ('partner', 'senior_associate', 'associate', 'paralegal')",
            name="ck_team_member_role",
        ),
    )

    member_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    practice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    can_approve: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 1:N relationships (as documented in docs/data-schema.md §4)
    matter_assignments: Mapped[list[MatterAssignment]] = relationship(
        "MatterAssignment", back_populates="member"
    )
    requests: Mapped[list[Request]] = relationship(
        "Request", back_populates="requester"
    )
    access_decisions: Mapped[list[AccessDecision]] = relationship(
        "AccessDecision", back_populates="member"
    )
    owned_obligations: Mapped[list[Obligation]] = relationship(
        "Obligation", back_populates="owner"
    )
    routed_escalations: Mapped[list[Escalation]] = relationship(
        "Escalation", back_populates="routed_to"
    )
    approval_decisions: Mapped[list[ApprovalDecision]] = relationship(
        "ApprovalDecision", back_populates="reviewer"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        "AuditEvent", back_populates="actor"
    )
    # The platform account(s) mapped to this firm member (0..1 by convention —
    # the demos use exactly one account per member, but the schema allows more).
    user: Mapped[Optional[User]] = relationship(
        "User", back_populates="member", uselist=False
    )

    def __repr__(self) -> str:
        return f"<TeamMember member_id={self.member_id!r} role={self.role!r}>"