"""Add status, reviewed_by, reviewed_at, reviewer_notes to finding table.

Revision ID: 20260826_003000
Revises: 20260826_002531
Create Date: 2026-08-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260826_003000"
down_revision = "20260826_002531"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "finding",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
    )
    op.add_column(
        "finding",
        sa.Column(
            "reviewed_by",
            sa.Text(),
            sa.ForeignKey("team_member.member_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "finding",
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "finding",
        sa.Column(
            "reviewer_notes",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("finding", "reviewer_notes")
    op.drop_column("finding", "reviewed_at")
    op.drop_column("finding", "reviewed_by")
    op.drop_column("finding", "status")
