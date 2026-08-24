"""Request model — incoming work item plus lifecycle status (FR-001–FR-003, FR-033)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.access_decision import AccessDecision
    from app.models.audit_event import AuditEvent
    from app.models.draft import Draft
    from app.models.escalation import Escalation
    from app.models.finding import Finding
    from app.models.organisation import Organisation
    from app.models.team_member import TeamMember


class Request(Base):
    """An incoming request about a client matter.

    Natural primary key ``request_id`` (``L-C-xxx``) is preserved from the
    supplied request files; new requests may use generated UUIDs.
    ``raw_content`` is never an input to access-decision logic (SEC-003).
    """

    __tablename__ = "request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('intake', 'classified', 'access_denied', 'processing', "
            "'escalated', 'drafted', 'awaiting_approval', 'approved', "
            "'edited', 'rejected', 'insufficient')",
            name="ck_request_status",
        ),
    )

    request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    requester_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("team_member.member_id"),
        nullable=False,
    )
    org_id: Mapped[Optional[str]] = mapped_column(
        Text,
        ForeignKey("organisation.org_id"),
        nullable=True,
    )
    request_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships (as documented in docs/data-schema.md §4)
    requester: Mapped[TeamMember] = relationship(
        "TeamMember", back_populates="requests"
    )
    organisation: Mapped[Optional[Organisation]] = relationship(
        "Organisation", back_populates="requests"
    )
    access_decisions: Mapped[list[AccessDecision]] = relationship(
        "AccessDecision", back_populates="request"
    )
    findings: Mapped[list[Finding]] = relationship(
        "Finding", back_populates="request"
    )
    drafts: Mapped[list[Draft]] = relationship(
        "Draft", back_populates="request"
    )
    escalations: Mapped[list[Escalation]] = relationship(
        "Escalation", back_populates="request"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        "AuditEvent", back_populates="request"
    )

    def __repr__(self) -> str:
        return (
            f"<Request request_id={self.request_id!r} "
            f"status={self.status!r}>"
        )