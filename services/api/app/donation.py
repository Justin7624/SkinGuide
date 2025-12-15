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

    # Dedupe
    existing = db.query(models.DonatedSample).filter(models.DonatedSample.roi_sha256 == roi_sha256).first()
    if existing:
        return (False, "duplicate")

    # Sharded directory (avoid huge single folder)
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
    )
    db.add(rec)
    db.commit()
    return (True, "stored")
