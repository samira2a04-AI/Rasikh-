"""Finding model — atomic citable output of review/consultation (FR-011, FR-019)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.citation import Citation
    from app.models.request import Request


class Finding(Base):
    """A single finding produced for a request.

    ``grounded=True`` requires at least one Citation; ``grounded=False``
    (explicit "not in the documents") requires zero Citation rows. Both rules
    are application-level checks, not database constraints. ``risk_rating``
    values come from the rulebook risk taxonomy at runtime.
    """

    __tablename__ = "finding"
    __table_args__ = (
        Index("ix_finding_request_id", "request_id"),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("request.request_id"),
        nullable=False,
    )
    checklist_area: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_rating: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sharia_sensitive_flag: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    tricky_case_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships (as documented in docs/data-schema.md §4)
    request: Mapped[Request] = relationship(
        "Request", back_populates="findings"
    )
    citations: Mapped[list[Citation]] = relationship(
        "Citation", back_populates="finding"
    )

    def __repr__(self) -> str:
        return (
            f"<Finding finding_id={self.finding_id!r} "
            f"grounded={self.grounded!r}>"
        )