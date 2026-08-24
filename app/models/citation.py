"""Citation model — links a Finding to a real source clause (GRD-002–GRD-005)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.contract_clause import ContractClause
    from app.models.finding import Finding
    from app.models.review_standard_clause import ReviewStandardClause


class Citation(Base):
    """A citation from a finding to exactly one source clause.

    ``source_type`` selects the source; the FK columns make inventing a
    non-existent clause impossible at the database level (GRD-004). The
    CHECK constraint enforces that exactly one of ``contract_clause_id`` /
    ``standard_clause_id`` is non-null.
    """

    __tablename__ = "citation"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('contract_clause', 'standard_clause')",
            name="ck_citation_source_type",
        ),
        CheckConstraint(
            "(contract_clause_id IS NOT NULL AND standard_clause_id IS NULL) "
            "OR (contract_clause_id IS NULL AND standard_clause_id IS NOT NULL)",
            name="ck_citation_exactly_one_source",
        ),
        Index("ix_citation_finding_id", "finding_id"),
    )

    citation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("finding.finding_id"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    contract_clause_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract_clause.clause_id"),
        nullable=True,
    )
    standard_clause_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_standard_clause.standard_clause_id"),
        nullable=True,
    )

    # Relationships (as documented in docs/data-schema.md §4)
    finding: Mapped[Finding] = relationship(
        "Finding", back_populates="citations"
    )
    contract_clause: Mapped[Optional[ContractClause]] = relationship(
        "ContractClause", back_populates="citations"
    )
    standard_clause: Mapped[Optional[ReviewStandardClause]] = relationship(
        "ReviewStandardClause", back_populates="citations"
    )

    def __repr__(self) -> str:
        return (
            f"<Citation citation_id={self.citation_id!r} "
            f"source_type={self.source_type!r}>"
        )