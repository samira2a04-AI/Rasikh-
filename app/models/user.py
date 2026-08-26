"""User model — authentication identity for the platform.

Passwords are stored as bcrypt hashes, never in plaintext. ``role`` is the
minimal authorization attribute; authorization enforcement lives in the
reusable dependencies in ``app.api.auth_dependencies``.

A user may optionally be linked to a firm/team member (``member_id``) so the
authenticated identity maps to the ``TeamMember`` that owns requests
(``Request.requester_id``). The link is nullable: self-registered accounts
without a roster record still authenticate, but cannot author a request until
they are mapped to a team member.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.team_member import TeamMember


class User(Base):
    """A platform user that can authenticate with email + password.

    ``role`` is the minimal authorization attribute:
    - ``member`` — normal workspace access (default)
    - ``admin``  — additionally may run administrative operations
                   (e.g. POST /obligations/sweep)

    Authorization lives here only as data; enforcement happens through the
    reusable dependencies in ``app.api.auth_dependencies``.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('member', 'admin')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="member",
        server_default=text("'member'"),
    )
    member_id: Mapped[Optional[str]] = mapped_column(
        Text,
        ForeignKey("team_member.member_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # The firm/team member this account maps to (owns its authored requests).
    member: Mapped[Optional[TeamMember]] = relationship(
        "TeamMember", back_populates="user"
    )

    def __repr__(self) -> str:
        return (
            f"<User id={self.id!r} email={self.email!r} active={self.is_active!r} "
            f"role={self.role!r} member_id={self.member_id!r}>"
        )

