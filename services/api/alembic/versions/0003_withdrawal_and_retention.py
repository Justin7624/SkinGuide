"""withdrawal and retention

Revision ID: 0003_withdrawal_and_retention
Revises: 0002_session_device_hash
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_withdrawal_and_retention"
down_revision = "0002_session_device_hash"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("donated_samples", sa.Column("is_withdrawn", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("donated_samples", sa.Column("withdrawn_at", sa.DateTime(), nullable=True))
    op.create_index("ix_donated_samples_is_withdrawn", "donated_samples", ["is_withdrawn"])

def downgrade():
    op.drop_index("ix_donated_samples_is_withdrawn", table_name="donated_samples")
    op.drop_column("donated_samples", "withdrawn_at")
    op.drop_column("donated_samples", "is_withdrawn")
