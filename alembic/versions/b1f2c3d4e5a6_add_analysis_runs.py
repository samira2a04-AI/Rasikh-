"""Add analysis_run table and finding.analysis_run_id

Revision ID: b1f2c3d4e5a6
Revises: d00efa545c34
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b1f2c3d4e5a6'
down_revision: Union[str, Sequence[str], None] = 'd00efa545c34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create analysis_run; link findings to their run (nullable for legacy rows)."""
    op.create_table(
        'analysis_run',
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'request_id',
            sa.Text(),
            sa.ForeignKey('request.request_id'),
            nullable=False,
        ),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('engine', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('finding_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('high_severity_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('grounded_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ungrounded_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_analysis_run_request_id', 'analysis_run', ['request_id']
    )
    # Legacy findings keep analysis_run_id NULL and remain valid; all NEW
    # findings are created with a run by app.services.workflow.run_review.
    op.add_column(
        'finding',
        sa.Column(
            'analysis_run_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('analysis_run.analysis_run_id'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('finding', 'analysis_run_id')
    op.drop_index('ix_analysis_run_request_id', table_name='analysis_run')
    op.drop_table('analysis_run')