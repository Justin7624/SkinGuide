# services/api/app/models.py

from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base

# --------------------------
# End-user tables
# --------------------------

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

    roi_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    result_json: Mapped[str] = mapped_column(Text)

    session: Mapped["Session"] = relationship(back_populates="progress")


class DonatedSample(Base):
    __tablename__ = "donated_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roi_sha256: Mapped[str] = mapped_column(String, unique=True, index=True)
    roi_image_path: Mapped[str] = mapped_column(String)
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


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String, index=True)

    body_markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    event_type: Mapped[str] = mapped_column(String, index=True)

    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    client_ip: Mapped[str | None] = mapped_column(String, nullable=True)

    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)


# --------------------------
# Admin RBAC + server sessions
# --------------------------

class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)

    # roles: "viewer" (read-only), "labeler" (label queue), "admin" (full)
    role: Mapped[str] = mapped_column(String, default="viewer", index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["AdminSession"]] = relationship(back_populates="user")


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # opaque token presented by cookie or Bearer
    token: Mapped[str] = mapped_column(String, unique=True, index=True)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_users.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # CSRF token for cookie-based web requests
    csrf_token: Mapped[str] = mapped_column(String, index=True)

    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["AdminUser"] = relationship(back_populates="sessions")
