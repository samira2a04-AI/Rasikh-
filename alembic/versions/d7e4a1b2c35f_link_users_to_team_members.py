"""link users to team members (authenticated requester resolution)

Revision ID: d7e4a1b2c35f
Revises: c5d9e2f81a47
Create Date: 2026-08-25

Adds a nullable ``users.member_id`` foreign key to ``team_member.member_id`` so
an authenticated user can be mapped to the firm/team-member identity that owns
their requests (e.g. ``Request.requester_id``).

The column is nullable because not every account is required to map to a roster
member (self-registered accounts may have no firm identity), and the check is
enforced at the application layer where a request is actually authored.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7e4a1b2c35f"
down_revision: Union[str, Sequence[str], None] = "c5d9e2f81a47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable member_id FK on users."""
    op.add_column(
        "users",
        sa.Column("member_id", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_member_id_team_member",
        "users",
        "team_member",
        ["member_id"],
        ["member_id"],
    )


def downgrade() -> None:
    """Remove the member_id FK and column."""
    op.drop_constraint("fk_users_member_id_team_member", "users", type_="foreignkey")
    op.drop_column("users", "member_id")
