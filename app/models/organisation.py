"""Organisation model — client organisations; the access-scoping unit ("matter")."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.data_room_file import DataRoomFile
    from app.models.matter_assignment import MatterAssignment
    from app.models.obligation import Obligation
    from app.models.request import Request


class Organisation(Base):
    """A client organisation (``ORG-xxxx``).

    Per docs/data-schema.md, Organisation is the access-scoping unit: access,
    obligations, contracts, files, and requests are all scoped by ``org_id``.
    Natural primary key ``org_id`` is preserved from ``organizations.json``.
    """

    __tablename__ = "organisation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'dormant')",
            name="ck_organisation_status",
        ),
    )

    org_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    # 1:N relationships (as documented in docs/data-schema.md §4)
    contracts: Mapped[list[Contract]] = relationship(
        "Contract", back_populates="organisation"
    )
    data_room_files: Mapped[list[DataRoomFile]] = relationship(
        "DataRoomFile", back_populates="organisation"
    )
    obligations: Mapped[list[Obligation]] = relationship(
        "Obligation", back_populates="organisation"
    )
    requests: Mapped[list[Request]] = relationship(
        "Request", back_populates="organisation"
    )
    matter_assignments: Mapped[list[MatterAssignment]] = relationship(
        "MatterAssignment", back_populates="organisation"
    )

    def __repr__(self) -> str:
        return f"<Organisation org_id={self.org_id!r} status={self.status!r}>"