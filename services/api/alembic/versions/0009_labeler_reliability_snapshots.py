"""labeler reliability snapshots

Revision ID: 0009_labeler_reliability_snapshots
Revises: 0008_consensus_artifacts
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_labeler_reliability_snapshots"
down_revision = "0008_consensus_artifacts"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "labeler_reliability_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("admin_email", sa.String(), nullable=True),
        sa.Column("n_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mean_abs_error", sa.Float(), nullable=True),
        sa.Column("reliability", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_lrs_created_at", "labeler_reliability_snapshots", ["created_at"])
    op.create_index("ix_lrs_window_days", "labeler_reliability_snapshots", ["window_days"])
    op.create_index("ix_lrs_admin_user_id", "labeler_reliability_snapshots", ["admin_user_id"])
    op.create_index("ix_lrs_admin_email", "labeler_reliability_snapshots", ["admin_email"])

def downgrade():
    op.drop_index("ix_lrs_admin_email", table_name="labeler_reliability_snapshots")
    op.drop_index("ix_lrs_admin_user_id", table_name="labeler_reliability_snapshots")
    op.drop_index("ix_lrs_window_days", table_name="labeler_reliability_snapshots")
    op.drop_index("ix_lrs_created_at", table_name="labeler_reliability_snapshots")
    op.drop_table("labeler_reliability_snapshots")
