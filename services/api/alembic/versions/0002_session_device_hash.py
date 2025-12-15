"""session device hash

Revision ID: 0002_session_device_hash
Revises: 0001_init
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_session_device_hash"
down_revision = "0001_init"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("sessions", sa.Column("device_token_hash", sa.String(), nullable=True))
    op.create_index("ix_sessions_device_token_hash", "sessions", ["device_token_hash"])

def downgrade():
    op.drop_index("ix_sessions_device_token_hash", table_name="sessions")
    op.drop_column("sessions", "device_token_hash")
