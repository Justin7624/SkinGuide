"""audit + legal docs + consent acceptance stamping

Revision ID: 0004_audit_and_legal_docs
Revises: 0003_withdrawal_and_retention
Create Date: 2025-12-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_audit_and_legal_docs"
down_revision = "0003_withdrawal_and_retention"
branch_labels = None
depends_on = None

def upgrade():
    # consent acceptance stamping
    op.add_column("consents", sa.Column("accepted_privacy_version", sa.String(), nullable=True))
    op.add_column("consents", sa.Column("accepted_terms_version", sa.String(), nullable=True))
    op.add_column("consents", sa.Column("accepted_consent_version", sa.String(), nullable=True))
    op.add_column("consents", sa.Column("accepted_at", sa.DateTime(), nullable=True))

    # policy_documents
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_policy_documents_key", "policy_documents", ["key"])
    op.create_index("ix_policy_documents_version", "policy_documents", ["version"])
    op.create_index("ix_policy_documents_is_active", "policy_documents", ["is_active"])

    # audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("client_ip", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])

def downgrade():
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_policy_documents_is_active", table_name="policy_documents")
    op.drop_index("ix_policy_documents_version", table_name="policy_documents")
    op.drop_index("ix_policy_documents_key", table_name="policy_documents")
    op.drop_table("policy_documents")

    op.drop_column("consents", "accepted_at")
    op.drop_column("consents", "accepted_consent_version")
    op.drop_column("consents", "accepted_terms_version")
    op.drop_column("consents", "accepted_privacy_version")
