"""AuditEvent model — append-only lifecycle record (FR-033, SEC-006, NFR-002/NFR-003)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Text, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.request import Request
    from app.models.team_member import TeamMember


class AuditEvent(Base):
    """One append-only lifecycle event.

    Rows are never updated or deleted; operational edits do not erase history.
    ``detail_reference`` points at the concrete row (table + id) behind the
    event and ``detail_json`` optionally carries a structured snapshot. The
    open-ended ``event_type`` list in the schema is intentionally not CHECK-
    constrained ("…" in docs/data-schema.md §3).
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_request_occurred_at", "request_id", "occurred_at"),
        Index("ix_audit_event_event_type_occurred_at", "event_type", "occurred_at"),
    )

    audit_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        Text,
        ForeignKey("request.request_id"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(
        Text,
        ForeignKey("team_member.member_id"),
        nullable=True,
    )
    detail_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detail_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Optional N:1 relationships (as documented in docs/data-schema.md §4)
    request: Mapped[Optional[Request]] = relationship(
        "Request", back_populates="audit_events"
    )
    actor: Mapped[Optional[TeamMember]] = relationship(
        "TeamMember", back_populates="audit_events"
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent event_type={self.event_type!r} "
            f"occurred_at={self.occurred_at!r}>"
        )