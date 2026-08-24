"""ReviewStandardClause model — the firm's ~35 numbered review-standard clauses."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.citation import Citation


class ReviewStandardClause(Base):
    """One numbered clause of the review standard ("0.1", "1.2", "3.3", …).

    Loaded from the six markdown files under ``rulebook/``. Risk-taxonomy
    labels, obligation thresholds, and escalation rules live inside these
    clauses and are read at runtime — never hard-coded in the schema.
    """

    __tablename__ = "review_standard_clause"
    __table_args__ = (
        UniqueConstraint(
            "clause_number",
            name="uq_review_standard_clause_clause_number",
        ),
    )

    standard_clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clause_number: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)

    # 1:N relationship (as documented in docs/data-schema.md §4)
    citations: Mapped[list[Citation]] = relationship(
        "Citation", back_populates="standard_clause"
    )

    def __repr__(self) -> str:
        return (
            f"<ReviewStandardClause number={self.clause_number!r} "
            f"category={self.category!r}>"
        )