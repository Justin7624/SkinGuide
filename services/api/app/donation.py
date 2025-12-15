# services/api/app/donation.py

import json
from sqlalchemy.orm import Session as OrmSession
from .config import settings
from . import models
from .storage import get_storage

def store_roi_donation(
    db: OrmSession,
    session_id: str,
    roi_sha256: str,
    roi_bytes: bytes,
    metadata: dict,
) -> tuple[bool, str]:
    if not settings.DONATION_STORAGE_ENABLED:
        return (False, "donation_storage_disabled")
    if not roi_sha256 or not roi_bytes:
        return (False, "missing_roi")

    existing = db.query(models.DonatedSample).filter(models.DonatedSample.roi_sha256 == roi_sha256).first()
    if existing:
        if existing.session_id == session_id:
            return (True, "already_donated")
        return (False, "duplicate_other_session")

    storage = get_storage()
    shard = roi_sha256[:2]
    key = f"donations/{shard}/{roi_sha256}.jpg"
    stored_obj = storage.put_bytes(data=roi_bytes, key=key, content_type="image/jpeg")

    rec = models.DonatedSample(
        session_id=session_id,
        roi_sha256=roi_sha256,
        roi_image_path=stored_obj.uri,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
        labels_json=None,
        labeled_at=None,
    )
    db.add(rec)
    db.commit()
    return (True, "stored")


def store_progress_roi(
    db: OrmSession,
    session_id: str,
    roi_sha256: str,
    roi_bytes: bytes,
    result_json_str: str,
) -> tuple[bool, str, str | None]:
    """
    Stores ROI-only progress image. Returns (stored, reason, uri_or_none).
    """
    if not settings.STORE_IMAGES_ENABLED:
        return (False, "progress_storage_disabled", None)
    if not roi_bytes:
        return (False, "missing_roi", None)

    storage = get_storage()
    shard = (roi_sha256[:2] if roi_sha256 else "xx")
    key = f"progress/{shard}/{roi_sha256 or 'nohash'}.jpg"
    stored_obj = storage.put_bytes(data=roi_bytes, key=key, content_type="image/jpeg")

    entry = models.ProgressEntry(
        session_id=session_id,
        roi_image_path=stored_obj.uri,
        result_json=result_json_str,
    )
    db.add(entry)
    db.commit()
    return (True, "stored", stored_obj.uri)
