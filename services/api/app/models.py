# services/api/app/models.py

from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device_token_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    consent: Mapped["Consent"] = relationship(back_populates="session", uselist=False)
    progress: Mapped[list["ProgressEntry"]] = relationship(back_populates="session")
    donations: Mapped[list["DonatedSample"]] = relationship(back_populates="session")


class Consent(Base):
    __tablename__ = "consents"
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), primary_key=True)

    store_progress_images: Mapped[bool] = mapped_column(Boolean, default=False)
    donate_for_improvement: Mapped[bool] = mapped_column(Boolean, default=False)

    # NEW: legal acceptance stamping (version strings)
    accepted_privacy_version: Mapped[str | None] = mapped_column(String, nullable=True)
    accepted_terms_version: Mapped[str | None] = mapped_column(String, nullable=True)
    accepted_consent_version: Mapped[str | None] = mapped_column(String, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    session: Mapped["Session"] = relationship(back_populates="consent")


class ProgressEntry(Base):
    __tablename__ = "progress_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roi_image_path: Mapped[str | None] = mapped_column(String, nullable=True)  # uri string
    result_json: Mapped[str] = mapped_column(Text)

    session: Mapped["Session"] = relationship(back_populates="progress")


class DonatedSample(Base):
    __tablename__ = "donated_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roi_sha256: Mapped[str] = mapped_column(String, unique=True, index=True)
    roi_image_path: Mapped[str] = mapped_column(String)  # uri string
    metadata_json: Mapped[str] = mapped_column(Text)

    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="donations")


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    version: Mapped[str] = mapped_column(String, unique=True, index=True)
    model_uri: Mapped[str] = mapped_column(String)
    manifest_uri: Mapped[str] = mapped_column(String)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


# --- NEW: legal docs scaffolding ---

class PolicyDocument(Base):
    """
    Versioned legal/policy/copy docs.
    key examples: "privacy_policy", "terms_of_use", "consent_copy"
    version examples: "2025-12-14-v1"
    """
    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String, index=True)

    body_markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


# --- NEW: audit trail ---

class AuditEvent(Base):
    """
    Append-only audit log for admin dashboards & compliance evidence.
    Do not store raw images, bearer tokens, device tokens, etc.
    """
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    event_type: Mapped[str] = mapped_column(String, index=True)

    # Optional session attribution (hashed device is NOT stored here)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Request context (redacted)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    client_ip: Mapped[str | None] = mapped_column(String, nullable=True)

    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
