"""admin 2FA (TOTP) + password reset tokens

Revision ID: 0006_admin_2fa_and_password_reset
Revises: 0005_admin_rbac_sessions_label_queue
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_admin_2fa_and_password_reset"
down_revision = "0005_admin_rbac_sessions_label_queue"
branch_labels = None
depends_on = None

def upgrade():
    # admin_users additions
    op.add_column("admin_users", sa.Column("totp_secret", sa.String(), nullable=True))
    op.add_column("admin_users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("admin_users", sa.Column("recovery_codes_json", sa.Text(), nullable=True))
    op.create_index("ix_admin_users_totp_enabled", "admin_users", ["totp_enabled"])

    # password reset tokens
    op.create_table(
        "admin_password_resets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
    )
    op.create_index("ix_admin_password_resets_user_id", "admin_password_resets", ["user_id"])
    op.create_index("ix_admin_password_resets_token_hash", "admin_password_resets", ["token_hash"], unique=True)
    op.create_index("ix_admin_password_resets_expires_at", "admin_password_resets", ["expires_at"])

def downgrade():
    op.drop_index("ix_admin_password_resets_expires_at", table_name="admin_password_resets")
    op.drop_index("ix_admin_password_resets_token_hash", table_name="admin_password_resets")
    op.drop_index("ix_admin_password_resets_user_id", table_name="admin_password_resets")
    op.drop_table("admin_password_resets")

    op.drop_index("ix_admin_users_totp_enabled", table_name="admin_users")
    op.drop_column("admin_users", "recovery_codes_json")
    op.drop_column("admin_users", "totp_enabled")
    op.drop_column("admin_users", "totp_secret")
