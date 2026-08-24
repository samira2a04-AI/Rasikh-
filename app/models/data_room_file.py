"""DataRoomFile model — non-contract matter files (6 supplied, DR-01 … DR-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.organisation import Organisation


class DataRoomFile(Base):
    """A data-room file belonging to a client organisation.

    Natural primary key ``file_id`` (``DR-01`` … ``DR-06``) is preserved from
    the supplied dataroom files. ``privileged=True`` marks files such as DR-04
    ("PRIVILEGED & CONFIDENTIAL — attorney work product"); privilege is
    enforced by an additional application-level check, not by this schema.
    """

    __tablename__ = "data_room_file"
    __table_args__ = (
        Index("ix_data_room_file_org_id", "org_id"),
    )

    file_id: Mapped[str] = mapped_column(Text, primary_key=True)
    org_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("organisation.org_id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    privileged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    content_uri: Mapped[str] = mapped_column(Text, nullable=False)

    # N:1 relationship (as documented in docs/data-schema.md §4)
    organisation: Mapped[Organisation] = relationship(
        "Organisation", back_populates="data_room_files"
    )

    def __repr__(self) -> str:
        return (
            f"<DataRoomFile file_id={self.file_id!r} "
            f"privileged={self.privileged!r}>"
        )