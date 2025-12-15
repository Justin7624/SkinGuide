# services/api/app/routes_admin_labelqueue.py

from __future__ import annotations

from datetime import datetime
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import asc

from .db import get_db
from . import models
from .security import require_role
from .storage import get_storage
from .audit import log_audit

router = APIRouter(prefix="/v1/admin/label-queue", tags=["admin-label-queue"])

# viewer can read; labeler+ can label
read_dep = Depends(require_role("viewer"))
label_dep = Depends(require_role("labeler"))

class QueueItem(BaseModel):
    id: int
    roi_sha256: str
    created_at: str
    image_url: str
    metadata_json: str = ""
    is_withdrawn: bool = False

class QueueResp(BaseModel):
    items: list[QueueItem] = Field(default_factory=list)

class LabelReq(BaseModel):
    labels: dict = Field(default_factory=dict)  # {attribute_key: 0..1}
    fitzpatrick: str | None = None
    age_band: str | None = None

class SkipReq(BaseModel):
    reason: str = "unclear"

@router.get("/next", response_model=QueueResp, dependencies=[read_dep])
def next_items(limit: int = 20, db: OrmSession = Depends(get_db)):
    limit = max(1, min(int(limit), 100))
    rows = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.is_(None))
        .order_by(asc(models.DonatedSample.created_at))
        .limit(limit)
        .all()
    )

    storage = get_storage()
    items: list[QueueItem] = []
    for d in rows:
        img_url = ""
        if d.roi_image_path.startswith("s3://"):
            img_url = storage.presign_get_url(d.roi_image_path, expires_sec=900) or ""
        else:
            img_url = f"/v1/admin/label-queue/roi/{d.id}"

        items.append(QueueItem(
            id=d.id,
            roi_sha256=d.roi_sha256,
            created_at=d.created_at.isoformat(),
            image_url=img_url,
            metadata_json=d.metadata_json or "",
            is_withdrawn=bool(d.is_withdrawn),
        ))

    return QueueResp(items=items)

@router.get("/roi/{donation_id}", dependencies=[read_dep])
def stream_roi(donation_id: int, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")

    storage = get_storage()
    lp = storage.get_local_path_if_any(d.roi_image_path)
    if not lp:
        raise HTTPException(400, "ROI not local; use presigned URL")

    return FileResponse(lp, media_type="image/jpeg")

@router.post("/{donation_id}/label", dependencies=[label_dep])
def label_item(donation_id: int, payload: LabelReq, request: Request, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")
    if d.labels_json is not None:
        raise HTTPException(409, "Already labeled")

    labels_payload = {
        "labels": payload.labels or {},
        "fitzpatrick": payload.fitzpatrick,
        "age_band": payload.age_band,
        "labeled_by": getattr(request.state.admin_user, "email", None),
        "labeled_via": "admin_queue",
    }
    d.labels_json = json.dumps(labels_payload, ensure_ascii=False)
    d.labeled_at = datetime.utcnow()

    log_audit(
        db,
        event_type="admin_label_applied",
        session_id=None,
        request=request,
        payload={"roi_sha256": d.roi_sha256, "label_keys": list((payload.labels or {}).keys())},
    )

    db.commit()
    return {"ok": True, "roi_sha256": d.roi_sha256}

@router.post("/{donation_id}/skip", dependencies=[label_dep])
def skip_item(donation_id: int, payload: SkipReq, request: Request, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")
    if d.labels_json is not None:
        raise HTTPException(409, "Already labeled")

    # Mark as "skipped" (trainer ignores because it won’t include label keys)
    d.labels_json = json.dumps(
        {"skipped": True, "reason": payload.reason, "skipped_by": getattr(request.state.admin_user, "email", None)},
        ensure_ascii=False,
    )
    d.labeled_at = datetime.utcnow()

    log_audit(
        db,
        event_type="admin_label_skipped",
        session_id=None,
        request=request,
        payload={"roi_sha256": d.roi_sha256},
    )

    db.commit()
    return {"ok": True, "roi_sha256": d.roi_sha256}
