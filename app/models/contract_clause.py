"""ContractClause model — clause-level unit for citation (GRD-003, FR-021)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, Text, text as sa_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.citation import Citation
    from app.models.contract import Contract


class ContractClause(Base):
    """A clause chunked out of a contract's full text at load time.

    ``clause_label`` is the clause number as it appears in the contract
    ("1", "7.2", …). Arabic clauses keep their original Arabic text.
    """

    __tablename__ = "contract_clause"
    __table_args__ = (
        # UNIQUE (contract_id, clause_label) where clause_label is not null —
        # implemented as a partial unique index per docs/data-schema.md §3.
        Index(
            "uq_contract_clause_contract_label",
            "contract_id",
            "clause_label",
            unique=True,
            postgresql_where=sa_text("clause_label IS NOT NULL"),
        ),
    )

    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("contract.contract_id"),
        nullable=False,
    )
    clause_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    checklist_area: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships (as documented in docs/data-schema.md §4)
    contract: Mapped[Contract] = relationship(
        "Contract", back_populates="clauses"
    )
    citations: Mapped[list[Citation]] = relationship(
        "Citation", back_populates="contract_clause"
    )

    def __repr__(self) -> str:
        return (
            f"<ContractClause clause_id={self.clause_id!r} "
            f"contract_id={self.contract_id!r} label={self.clause_label!r}>"
        )