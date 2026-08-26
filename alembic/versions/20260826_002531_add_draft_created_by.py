"""Add created_by to drafts for approval separation of duties (APR-006).

Revision ID: 20260826_002531_add_draft_created_by
Revises: b1f2c3d4e5a6_add_analysis_runs
Create Date: 2026-08-26

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260826_002531"
down_revision = "b1f2c3d4e5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "draft",
        sa.Column(
            "created_by",
            sa.Text(),
            sa.ForeignKey("team_member.member_id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_constraint("fk_draft_created_by", "draft", type_="foreignkey")
    op.drop_column("draft", "created_by")