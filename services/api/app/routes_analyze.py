# services/api/app/routes_analyze.py

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session as OrmSession
from .db import get_db
from .config import settings
from .security import rate_limit_or_429
from . import models, schemas
import httpx
import os
import json
import uuid
import base64

router = APIRouter(prefix="/v1", tags=["analyze"])

DISCLAIMER = "Cosmetic/appearance guidance only. Not a medical diagnosis or medical advice."

def build_plan(attributes, quality):
    """
    Rule-based, non-diagnostic recommender that maps appearance attributes -> routine suggestions.
    Uses conservative outputs when image quality is poor.
    """
    s = {a["key"]: a["score"] for a in attributes}

    conservative = (
        quality.get("lighting") != "ok"
        or quality.get("blur") == "high"
        or quality.get("angle") != "ok"
    )

    routine_am = ["Gentle cleanser", "Barrier moisturizer", "Broad-spectrum SPF 30+"]
    routine_pm = ["Gentle cleanser", "Moisturizer"]

    pro = []
    seek_care = [
        "Seek care for rapidly changing spots, bleeding lesions, severe pain, or persistent worsening."
    ]

    if not conservative and s.get("uneven_tone_appearance", 0) > 0.6:
        routine_am.insert(1, "Vitamin C (start low, patch test)")
        pro.append("Discuss IPL/laser options for uneven tone appearance with a qualified clinician.")

    if s.get("redness_appearance", 0) > 0.6:
        routine_am = ["Gentle cleanser (no scrubs)", "Barrier moisturizer", "SPF 30+"]
        routine_pm = ["Gentle cleanser", "Barrier moisturizer"]
        seek_care.append("Persistent redness/burning: consider clinician evaluation (not a diagnosis).")

    if not conservative and s.get("texture_roughness_appearance", 0) > 0.6:
        routine_pm.append("Retinoid: start 2 nights/week if tolerated")
        routine_pm.append("Optional: BHA 2–3x/week (not on retinoid nights)")
        pro.append("Discuss RF microneedling or resurfacing options based on your skin type and goals.")

    return {"routine": {"AM": routine_am, "PM": routine_pm}, "pro": pro, "seek_care": seek_care}


@router.post("/analyze", response_model=schemas.AnalyzeResponse)
async def analyze(
    session_id: str,
    image: UploadFile = File(...),
    db: OrmSession = Depends(get_db)
):
    # Rate limiting per session
    if not rate_limit_or_429(session_id):
        raise HTTPException(429, "Too many requests. Try again soon.")

    # Basic validation
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Upload a JPG or PNG.")

    data = await image.read()
    if len(data) > settings.MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(413, "Image too large.")

    # Validate session
    s = db.get(models.Session, session_id)
    if not s:
        raise HTTPException(404, "Session not found")

    # Consent (default: false/false)
    c = db.get(models.Consent, session_id)
    store_progress = bool(c.store_progress_images) if c else False
    donate = bool(c.donate_for_improvement) if c else False

    # Call ML service. Ask it to return ROI jpeg (base64) so we can store ROI only (opt-in).
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
                settings.ML_URL,
                files={"image": data},
                headers={"X-Return-ROI": "1"},
            )
    except httpx.RequestError:
        raise HTTPException(502, "Inference service unavailable")

    # ML may reject if it can't isolate a usable ROI
    if r.status_code == 422:
        raise HTTPException(422, "Unable to isolate face/skin ROI. Try better lighting and a straight-on angle.")
    if r.status_code != 200:
        raise HTTPException(502, "Inference service error")

    payload = r.json()

    plan = build_plan(payload["attributes"], payload["quality"])

    resp = {
        "disclaimer": DISCLAIMER,
        "quality": payload["quality"],
        "attributes": payload["attributes"],
        # NEW: include region breakdown
        "regions": payload.get("regions", []),
        "routine": plan["routine"],
        "professional_to_discuss": plan["pro"],
        "when_to_seek_care": plan["seek_care"],
        "model_version": payload["model_version"],
        "stored_for_progress": False,
    }

    # Decode ROI bytes (NOT the original upload) for storage
    roi_b64 = payload.get("roi_jpeg_b64")
    roi_bytes = None
    if roi_b64:
        try:
            roi_bytes = base64.b64decode(roi_b64.encode("ascii"))
        except Exception:
            roi_bytes = None

    # Store progress ONLY if user opted in AND server storage enabled AND we have ROI bytes
    if store_progress and settings.STORE_IMAGES_ENABLED and roi_bytes:
        os.makedirs(settings.IMAGE_STORE_DIR, exist_ok=True)

        roi_sha = (payload.get("roi_sha256") or "")[:12]
        fname = f"{uuid.uuid4()}_{roi_sha}.jpg" if roi_sha else f"{uuid.uuid4()}.jpg"
        fpath = os.path.join(settings.IMAGE_STORE_DIR, fname)

        with open(fpath, "wb") as f:
            f.write(roi_bytes)

        entry = models.ProgressEntry(
            session_id=session_id,
            roi_image_path=fpath,
            result_json=json.dumps(resp),
        )
        db.add(entry)
        db.commit()
        resp["stored_for_progress"] = True

    # Donate for improvement (placeholder)
    # In production: enqueue ROI hash + metadata to a secure pipeline (only if opted in).
    if donate:
        # no-op in MVP
        pass

    return resp
