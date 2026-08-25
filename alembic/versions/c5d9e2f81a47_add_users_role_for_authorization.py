"""add role column to users for authorization

Revision ID: c5d9e2f81a47
Revises: a7f3c1d94b20
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d9e2f81a47'
down_revision: Union[str, Sequence[str], None] = 'a7f3c1d94b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the minimal role attribute ('member' | 'admin') to users."""
    op.add_column(
        'users',
        sa.Column(
            'role',
            sa.Text(),
            nullable=False,
            server_default=sa.text("'member'"),
        ),
    )
    op.create_check_constraint('ck_users_role', 'users', "role IN ('member', 'admin')")


def downgrade() -> None:
    """Remove the role column."""
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.drop_column('users', 'role')
