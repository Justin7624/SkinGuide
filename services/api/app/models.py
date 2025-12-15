# services/api/app/models.py

from sqlalchemy import (
    String, Boolean, DateTime, Integer, ForeignKey, Text, Float
)
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
    label_submissions: Mapped[list["DonatedSampleLabel"]] = relationship(back_populates="donated_sample")
    consensus_artifacts: Mapped[list["ConsensusArtifact"]] = relationship(back_populates="donated_sample")


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    version: Mapped[str] = mapped_column(String, unique=True, index=True)
    model_uri: Mapped[str] = mapped_column(String)
    manifest_uri: Mapped[str] = mapped_column(String)

    # NEW: separate markdown model card location (local path or s3://...)
    model_card_uri: Mapped[str | None] = mapped_column(String, nullable=True)

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
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    path: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    method: Mapped[str | None] = mapped_column(String, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    actor_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    admin_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    admin_email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)


# --------------------------
# Admin RBAC + server sessions + 2FA + reset
# --------------------------

class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)

    role: Mapped[str] = mapped_column(String, default="viewer", index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    totp_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    recovery_codes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    sessions: Mapped[list["AdminSession"]] = relationship(back_populates="user")
    resets: Mapped[list["AdminPasswordReset"]] = relationship(back_populates="user")
    labels: Mapped[list["DonatedSampleLabel"]] = relationship(back_populates="admin_user")


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_users.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    csrf_token: Mapped[str] = mapped_column(String, index=True)

    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["AdminUser"] = relationship(back_populates="sessions")


class AdminPasswordReset(Base):
    __tablename__ = "admin_password_resets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_users.id"), index=True)

    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["AdminUser"] = relationship(back_populates="resets")


# --------------------------
# Label submissions (consensus)
# --------------------------

class DonatedSampleLabel(Base):
    __tablename__ = "donated_sample_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    donated_sample_id: Mapped[int] = mapped_column(Integer, ForeignKey("donated_samples.id"), index=True)
    admin_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_users.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    is_skip: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    labels_json: Mapped[str] = mapped_column(Text)

    donated_sample: Mapped["DonatedSample"] = relationship(back_populates="label_submissions")
    admin_user: Mapped["AdminUser"] = relationship(back_populates="labels")


# --------------------------
# Consensus audit artifacts
# --------------------------

class ConsensusArtifact(Base):
    __tablename__ = "consensus_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    donated_sample_id: Mapped[int] = mapped_column(Integer, ForeignKey("donated_samples.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    status: Mapped[str] = mapped_column(String, index=True)
    algorithm: Mapped[str] = mapped_column(String, default="median/mean_consensus", index=True)

    computed_by_admin_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    computed_by_admin_email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    artifact_json: Mapped[str] = mapped_column(Text)

    donated_sample: Mapped["DonatedSample"] = relationship(back_populates="consensus_artifacts")


# --------------------------
# Labeler reliability snapshots (nightly)
# --------------------------

class LabelerReliabilitySnapshot(Base):
    __tablename__ = "labeler_reliability_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    window_days: Mapped[int] = mapped_column(Integer, default=180, index=True)

    admin_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin_users.id"), index=True)
    admin_email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    n_samples: Mapped[int] = mapped_column(Integer, default=0)

    mean_abs_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    reliability: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
