"""add model_card_uri to model_artifacts

Revision ID: 0010_model_card_uri
Revises: 0009_labeler_reliability_snapshots
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_model_card_uri"
down_revision = "0009_labeler_reliability_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("model_artifacts", sa.Column("model_card_uri", sa.String(), nullable=True))


def downgrade():
    op.drop_column("model_artifacts", "model_card_uri")
