"""Contract model — matter contracts (12 supplied, C-01 … C-12)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.contract_clause import ContractClause
    from app.models.organisation import Organisation


class Contract(Base):
    """A matter contract.

    Natural primary key ``contract_id`` (``C-01`` … ``C-12``) is preserved from
    the supplied contract files. ``org_id`` is the access unit; ``privileged``
    is enforced by a second, independent application-level check.
    """

    __tablename__ = "contract"
    __table_args__ = (
        CheckConstraint(
            "language IN ('en', 'ar')",
            name="ck_contract_language",
        ),
        Index("ix_contract_org_id", "org_id"),
    )

    contract_id: Mapped[str] = mapped_column(Text, primary_key=True)
    org_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("organisation.org_id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    privileged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    content_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships (as documented in docs/data-schema.md §4)
    organisation: Mapped[Organisation] = relationship(
        "Organisation", back_populates="contracts"
    )
    clauses: Mapped[list[ContractClause]] = relationship(
        "ContractClause", back_populates="contract"
    )

    def __repr__(self) -> str:
        return f"<Contract contract_id={self.contract_id!r} language={self.language!r}>"