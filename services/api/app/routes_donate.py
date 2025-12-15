# services/api/app/routes_donate.py

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session as OrmSession
from .db import get_db
from .config import settings
from .security import rate_limit_or_429
from . import models, schemas
from .donation import store_roi_donation
import httpx
import base64

router = APIRouter(prefix="/v1", tags=["donate"])

@router.post("/donate", response_model=schemas.DonateResponse)
async def donate(
    session_id: str,
    image: UploadFile = File(...),
    db: OrmSession = Depends(get_db),
):
    """
    Optional endpoint: user can explicitly donate a scan for model improvement.
    Still requires consent donate_for_improvement=true.
    Stores ROI-only, never full selfie.
    """
    if not rate_limit_or_429(session_id):
        raise HTTPException(429, "Too many requests. Try again soon.")

    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Upload a JPG or PNG.")

    data = await image.read()
    if len(data) > settings.MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(413, "Image too large.")

    s = db.get(models.Session, session_id)
    if not s:
        raise HTTPException(404, "Session not found")

    c = db.get(models.Consent, session_id)
    if not c or not bool(c.donate_for_improvement):
        return schemas.DonateResponse(ok=True, stored=False, reason="no_consent")

    # Ask ML for ROI bytes + sha. (ROI-only will be stored.)
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
                settings.ML_URL,
                files={"image": data},
                headers={"X-Return-ROI": "1"},
            )
    except httpx.RequestError:
        raise HTTPException(502, "Inference service unavailable")

    if r.status_code == 422:
        return schemas.DonateResponse(ok=True, stored=False, reason="roi_not_found")
    if r.status_code != 200:
        raise HTTPException(502, "Inference service error")

    payload = r.json()
    roi_b64 = payload.get("roi_jpeg_b64")
    roi_sha = payload.get("roi_sha256")

    roi_bytes = None
    if roi_b64:
        try:
            roi_bytes = base64.b64decode(roi_b64.encode("ascii"))
        except Exception:
            roi_bytes = None

    # Minimal metadata only (no identifiers)
    meta = {
        "model_version": payload.get("model_version"),
        "quality": payload.get("quality"),
        "attributes": payload.get("attributes"),
        "regions": payload.get("regions", []),
    }

    stored, reason = store_roi_donation(
        db=db,
        session_id=session_id,
        roi_sha256=roi_sha or "",
        roi_bytes=roi_bytes or b"",
        metadata=meta,
    )

    return schemas.DonateResponse(ok=True, stored=stored, reason=reason, roi_sha256=roi_sha)
