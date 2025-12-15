# services/api/app/models.py

from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    consent: Mapped["Consent"] = relationship(back_populates="session", uselist=False)
    progress: Mapped[list["ProgressEntry"]] = relationship(back_populates="session")
    donations: Mapped[list["DonatedSample"]] = relationship(back_populates="session")


class Consent(Base):
    __tablename__ = "consents"
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), primary_key=True)

    store_progress_images: Mapped[bool] = mapped_column(Boolean, default=False)
    donate_for_improvement: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    session: Mapped["Session"] = relationship(back_populates="consent")


class ProgressEntry(Base):
    __tablename__ = "progress_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Stores URI string (file://... or s3://...)
    roi_image_path: Mapped[str | None] = mapped_column(String, nullable=True)

    result_json: Mapped[str] = mapped_column(Text)
    session: Mapped["Session"] = relationship(back_populates="progress")


class DonatedSample(Base):
    __tablename__ = "donated_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roi_sha256: Mapped[str] = mapped_column(String, unique=True, index=True)

    # Stores URI string (file://... or s3://...)
    roi_image_path: Mapped[str] = mapped_column(String)

    metadata_json: Mapped[str] = mapped_column(Text)

    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="donations")


class ModelArtifact(Base):
    """
    Registry of trained model artifacts with metadata and controlled activation.
    Artifacts can live in local filesystem or S3; store as URI strings.
    """
    __tablename__ = "model_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    version: Mapped[str] = mapped_column(String, unique=True, index=True)

    # Where the model + manifest live (file://... or s3://...)
    model_uri: Mapped[str] = mapped_column(String)
    manifest_uri: Mapped[str] = mapped_column(String)

    # Optional metrics blob (json string)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Activation flag (only one should be active)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
