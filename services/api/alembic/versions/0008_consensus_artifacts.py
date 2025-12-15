"""consensus artifacts

Revision ID: 0008_consensus_artifacts
Revises: 0007_audit_hardening_and_label_consensus
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_consensus_artifacts"
down_revision = "0007_audit_hardening_and_label_consensus"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "consensus_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("donated_sample_id", sa.Integer(), sa.ForeignKey("donated_samples.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("algorithm", sa.String(), nullable=False, server_default="median/mean_consensus"),
        sa.Column("computed_by_admin_user_id", sa.Integer(), nullable=True),
        sa.Column("computed_by_admin_email", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("artifact_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_consensus_artifacts_sample", "consensus_artifacts", ["donated_sample_id"])
    op.create_index("ix_consensus_artifacts_created_at", "consensus_artifacts", ["created_at"])
    op.create_index("ix_consensus_artifacts_status", "consensus_artifacts", ["status"])
    op.create_index("ix_consensus_artifacts_algorithm", "consensus_artifacts", ["algorithm"])
    op.create_index("ix_consensus_artifacts_admin_id", "consensus_artifacts", ["computed_by_admin_user_id"])
    op.create_index("ix_consensus_artifacts_admin_email", "consensus_artifacts", ["computed_by_admin_email"])
    op.create_index("ix_consensus_artifacts_request_id", "consensus_artifacts", ["request_id"])

def downgrade():
    op.drop_index("ix_consensus_artifacts_request_id", table_name="consensus_artifacts")
    op.drop_index("ix_consensus_artifacts_admin_email", table_name="consensus_artifacts")
    op.drop_index("ix_consensus_artifacts_admin_id", table_name="consensus_artifacts")
    op.drop_index("ix_consensus_artifacts_algorithm", table_name="consensus_artifacts")
    op.drop_index("ix_consensus_artifacts_status", table_name="consensus_artifacts")
    op.drop_index("ix_consensus_artifacts_created_at", table_name="consensus_artifacts")
    op.drop_index("ix_consensus_artifacts_sample", table_name="consensus_artifacts")
    op.drop_table("consensus_artifacts")
