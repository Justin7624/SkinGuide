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

    # Default false. Explicit opt-in required.
    store_progress_images: Mapped[bool] = mapped_column(Boolean, default=False)
    donate_for_improvement: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["Session"] = relationship(back_populates="consent")


class ProgressEntry(Base):
    __tablename__ = "progress_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Stored only if user opted in AND storage enabled server-side
    roi_image_path: Mapped[str | None] = mapped_column(String, nullable=True)

    # JSON string to keep it simple in MVP
    result_json: Mapped[str] = mapped_column(Text)

    session: Mapped["Session"] = relationship(back_populates="progress")


class DonatedSample(Base):
    """
    ROI-only donation, consent-gated.
    Stores only a cropped/masked ROI (no full selfie), plus minimal metadata.
    Deduped by roi_sha256.
    """
    __tablename__ = "donated_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roi_sha256: Mapped[str] = mapped_column(String, unique=True, index=True)
    roi_image_path: Mapped[str] = mapped_column(String)

    # minimal metadata JSON (quality + attribute scores + model_version etc)
    metadata_json: Mapped[str] = mapped_column(Text)

    session: Mapped["Session"] = relationship(back_populates="donations")
