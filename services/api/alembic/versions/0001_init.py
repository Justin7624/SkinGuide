"""init

Revision ID: 0001_init
Revises: 
Create Date: 2025-12-14

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "consents",
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), primary_key=True),
        sa.Column("store_progress_images", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("donate_for_improvement", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "progress_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("roi_image_path", sa.String(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_progress_entries_session_id", "progress_entries", ["session_id"])

    op.create_table(
        "donated_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("roi_sha256", sa.String(), nullable=False, unique=True),
        sa.Column("roi_image_path", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("labels_json", sa.Text(), nullable=True),
        sa.Column("labeled_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_donated_samples_session_id", "donated_samples", ["session_id"])
    op.create_index("ix_donated_samples_roi_sha256", "donated_samples", ["roi_sha256"])

    op.create_table(
        "model_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.String(), nullable=False, unique=True),
        sa.Column("model_uri", sa.String(), nullable=False),
        sa.Column("manifest_uri", sa.String(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_model_artifacts_version", "model_artifacts", ["version"])

def downgrade():
    op.drop_index("ix_model_artifacts_version", table_name="model_artifacts")
    op.drop_table("model_artifacts")

    op.drop_index("ix_donated_samples_roi_sha256", table_name="donated_samples")
    op.drop_index("ix_donated_samples_session_id", table_name="donated_samples")
    op.drop_table("donated_samples")

    op.drop_index("ix_progress_entries_session_id", table_name="progress_entries")
    op.drop_table("progress_entries")

    op.drop_table("consents")
    op.drop_table("sessions")
