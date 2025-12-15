"""add model_deployments (canary rollout config)

Revision ID: 0011_model_deployments
Revises: 0010_model_card_uri
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_model_deployments"
down_revision = "0010_model_card_uri"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_deployments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),

        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),

        sa.Column("canary_model_id", sa.Integer(), sa.ForeignKey("model_artifacts.id"), nullable=True),
        sa.Column("canary_percent", sa.Integer(), nullable=False, server_default=sa.text("0")),

        sa.Column("auto_rollback_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_slice_mae_increase", sa.Float(), nullable=False, server_default=sa.text("0.03")),
        sa.Column("min_slice_n", sa.Integer(), nullable=False, server_default=sa.text("50")),

        sa.Column("last_check_at", sa.DateTime(), nullable=True),
        sa.Column("last_check_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_model_deployments_enabled", "model_deployments", ["enabled"])
    op.create_index("ix_model_deployments_canary_model_id", "model_deployments", ["canary_model_id"])


def downgrade():
    op.drop_index("ix_model_deployments_canary_model_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_enabled", table_name="model_deployments")
    op.drop_table("model_deployments")
