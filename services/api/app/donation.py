# services/api/app/donation.py

import os
import json
from sqlalchemy.orm import Session as OrmSession
from .config import settings
from . import models

def _safe_mkdir(path: str):
    os.makedirs(path, exist_ok=True)

def store_roi_donation(
    db: OrmSession,
    session_id: str,
    roi_sha256: str,
    roi_bytes: bytes,
    metadata: dict,
) -> tuple[bool, str]:
    """
    Stores ROI-only donation if enabled. Dedupes by roi_sha256.
    Returns (stored, reason).
    """
    if not settings.DONATION_STORAGE_ENABLED:
        return (False, "donation_storage_disabled")

    if not roi_sha256 or not roi_bytes:
        return (False, "missing_roi")

    existing = db.query(models.DonatedSample).filter(models.DonatedSample.roi_sha256 == roi_sha256).first()
    if existing:
        return (False, "duplicate")

    shard = roi_sha256[:2]
    dirpath = os.path.join(settings.DONATION_STORE_DIR, shard)
    _safe_mkdir(dirpath)

    fpath = os.path.join(dirpath, f"{roi_sha256}.jpg")
    if not os.path.exists(fpath):
        with open(fpath, "wb") as f:
            f.write(roi_bytes)

    rec = models.DonatedSample(
        session_id=session_id,
        roi_sha256=roi_sha256,
        roi_image_path=fpath,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
        labels_json=None,
        labeled_at=None,
    )
    db.add(rec)
    db.commit()
    return (True, "stored")


def store_labels_for_sample(
    db: OrmSession,
    session_id: str,
    roi_sha256: str,
    labels_payload: dict,
) -> tuple[bool, str]:
    """
    Stores labels for an existing donated sample.
    Also writes a JSON label file to DONATION_LABEL_DIR for trainer consumption.
    """
    if not settings.DONATION_STORAGE_ENABLED:
        return (False, "donation_storage_disabled")

    if not roi_sha256:
        return (False, "missing_roi_sha256")

    sample = db.query(models.DonatedSample).filter(models.DonatedSample.roi_sha256 == roi_sha256).first()
    if not sample:
        return (False, "sample_not_found")

    # Optional: ensure the session submitting labels matches the donating session
    # (you can relax this later if you add accounts/admin tooling)
    if sample.session_id != session_id:
        return (False, "not_owner")

    # Persist in DB
    from datetime import datetime
    sample.labels_json = json.dumps(labels_payload, ensure_ascii=False)
    sample.labeled_at = datetime.utcnow()
    db.commit()

    # Persist on disk for trainer
    _safe_mkdir(settings.DONATION_LABEL_DIR)
    label_path = os.path.join(settings.DONATION_LABEL_DIR, f"{roi_sha256}.json")
    with open(label_path, "w", encoding="utf-8") as f:
        json.dump(labels_payload, f, ensure_ascii=False, indent=2)

    return (True, "stored")
