"""audit hardening fields + donated_sample_labels for consensus

Revision ID: 0007_audit_hardening_and_label_consensus
Revises: 0006_admin_2fa_and_password_reset
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_audit_hardening_and_label_consensus"
down_revision = "0006_admin_2fa_and_password_reset"
branch_labels = None
depends_on = None

def upgrade():
    # audit_events columns
    op.add_column("audit_events", sa.Column("user_agent", sa.String(), nullable=True))
    op.add_column("audit_events", sa.Column("path", sa.String(), nullable=True))
    op.add_column("audit_events", sa.Column("method", sa.String(), nullable=True))
    op.add_column("audit_events", sa.Column("status_code", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("actor_type", sa.String(), nullable=True))
    op.add_column("audit_events", sa.Column("admin_user_id", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("admin_email", sa.String(), nullable=True))

    op.create_index("ix_audit_events_path", "audit_events", ["path"])
    op.create_index("ix_audit_events_actor_type", "audit_events", ["actor_type"])
    op.create_index("ix_audit_events_admin_user_id", "audit_events", ["admin_user_id"])
    op.create_index("ix_audit_events_admin_email", "audit_events", ["admin_email"])

    # donated_sample_labels table
    op.create_table(
        "donated_sample_labels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("donated_sample_id", sa.Integer(), sa.ForeignKey("donated_samples.id"), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("is_skip", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("labels_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_donated_sample_labels_sample", "donated_sample_labels", ["donated_sample_id"])
    op.create_index("ix_donated_sample_labels_admin", "donated_sample_labels", ["admin_user_id"])
    op.create_index("ix_donated_sample_labels_created_at", "donated_sample_labels", ["created_at"])
    op.create_index("ix_donated_sample_labels_is_skip", "donated_sample_labels", ["is_skip"])

    # Prevent same admin submitting twice for the same sample
    op.create_unique_constraint(
        "uq_donated_sample_labels_sample_admin",
        "donated_sample_labels",
        ["donated_sample_id", "admin_user_id"],
    )

def downgrade():
    op.drop_constraint("uq_donated_sample_labels_sample_admin", "donated_sample_labels", type_="unique")
    op.drop_index("ix_donated_sample_labels_is_skip", table_name="donated_sample_labels")
    op.drop_index("ix_donated_sample_labels_created_at", table_name="donated_sample_labels")
    op.drop_index("ix_donated_sample_labels_admin", table_name="donated_sample_labels")
    op.drop_index("ix_donated_sample_labels_sample", table_name="donated_sample_labels")
    op.drop_table("donated_sample_labels")

    op.drop_index("ix_audit_events_admin_email", table_name="audit_events")
    op.drop_index("ix_audit_events_admin_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_type", table_name="audit_events")
    op.drop_index("ix_audit_events_path", table_name="audit_events")

    op.drop_column("audit_events", "admin_email")
    op.drop_column("audit_events", "admin_user_id")
    op.drop_column("audit_events", "actor_type")
    op.drop_column("audit_events", "status_code")
    op.drop_column("audit_events", "method")
    op.drop_column("audit_events", "path")
    op.drop_column("audit_events", "user_agent")
