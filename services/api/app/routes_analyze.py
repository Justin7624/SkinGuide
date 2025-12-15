# services/api/app/routes_analyze.py

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Header, Request
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from .config import settings
from .security import rate_limit_or_429
from . import models, schemas
from .donation import store_roi_donation, store_progress_roi
from .auth import require_user_auth
from .image_safety import sanitize_upload_image
from .audit import log_audit

import httpx
import json
import base64

router = APIRouter(prefix="/v1", tags=["analyze"])

DISCLAIMER = "Cosmetic/appearance guidance only. Not a medical diagnosis or medical advice."

def build_plan(attributes, quality):
    s = {a["key"]: a["score"] for a in attributes}
    conservative = (quality.get("lighting") != "ok" or quality.get("blur") == "high" or quality.get("angle") != "ok")

    routine_am = ["Gentle cleanser", "Barrier moisturizer", "Broad-spectrum SPF 30+"]
    routine_pm = ["Gentle cleanser", "Moisturizer"]
    pro = []
    seek_care = ["Seek care for rapidly changing spots, bleeding lesions, severe pain, or persistent worsening."]

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
    request: Request,
    session_id: str | None = None,
    image: UploadFile = File(...),
    db: OrmSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
):
    session_id, _dvh = require_user_auth(db, session_id, authorization, x_device_token)

    if not rate_limit_or_429(session_id):
        raise HTTPException(429, "Too many requests. Try again soon.")

    raw = await image.read()
    if len(raw) > settings.MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(413, "Image too large.")

    try:
        sanitized = sanitize_upload_image(raw)
    except ValueError as e:
        code = str(e)
        if code == "unsupported_image_type":
            raise HTTPException(400, "Unsupported image type. Upload a JPEG or PNG.")
        if code == "decode_failed":
            raise HTTPException(400, "Could not decode image. Try exporting as a standard JPEG.")
        if code == "image_too_small":
            raise HTTPException(400, "Image too small. Move closer and ensure good lighting.")
        if code == "too_many_pixels":
            raise HTTPException(413, "Image resolution too large.")
        raise HTTPException(400, "Invalid image.")
    except Exception:
        raise HTTPException(400, "Invalid image.")

    s = db.get(models.Session, session_id)
    if not s:
        raise HTTPException(404, "Session not found")

    c = db.get(models.Consent, session_id)
    store_progress = bool(c.store_progress_images) if c else False
    donate_opt_in = bool(c.donate_for_improvement) if c else False

    log_audit(
        db,
        event_type="analyze_called",
        session_id=session_id,
        request=request,
        payload={"regions_count": None, "attributes_count": None},
    )
    db.commit()

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
                settings.ML_URL,
                files={"image": ("upload.jpg", sanitized.jpeg_bytes, "image/jpeg")},
                headers={"X-Return-ROI": "1"},
            )
    except httpx.RequestError:
        raise HTTPException(502, "Inference service unavailable")

    if r.status_code == 422:
        raise HTTPException(422, "Unable to isolate face/skin ROI. Try better lighting and a straight-on angle.")
    if r.status_code != 200:
        raise HTTPException(502, "Inference service error")

    payload = r.json()
    roi_sha = payload.get("roi_sha256") or ""
    plan = build_plan(payload["attributes"], payload["quality"])

    resp = {
        "disclaimer": DISCLAIMER,
        "quality": payload["quality"],
        "attributes": payload["attributes"],
        "regions": payload.get("regions", []),
        "routine": plan["routine"],
        "professional_to_discuss": plan["pro"],
        "when_to_seek_care": plan["seek_care"],
        "model_version": payload["model_version"],
        "stored_for_progress": False,
        "roi_sha256": roi_sha or None,
        "donation": {"enabled": bool(donate_opt_in), "stored": False, "reason": None, "roi_sha256": roi_sha or None},
    }

    roi_b64 = payload.get("roi_jpeg_b64")
    roi_bytes = None
    if roi_b64:
        try:
            roi_bytes = base64.b64decode(roi_b64.encode("ascii"))
        except Exception:
            roi_bytes = None

    if store_progress and roi_bytes:
        stored, _reason, _uri = store_progress_roi(
            db=db,
            session_id=session_id,
            roi_sha256=roi_sha,
            roi_bytes=roi_bytes,
            result_json_str=json.dumps(resp),
        )
        resp["stored_for_progress"] = bool(stored)

    donation_stored = False
    donation_reason = None
    if donate_opt_in:
        if not roi_bytes or not roi_sha:
            donation_stored = False
            donation_reason = "missing_roi"
            resp["donation"]["stored"] = False
            resp["donation"]["reason"] = donation_reason
        else:
            meta = {
                "model_version": payload.get("model_version"),
                "quality": payload.get("quality"),
                "attributes": payload.get("attributes"),
                "regions": payload.get("regions", []),
            }
            donation_stored, donation_reason = store_roi_donation(
                db=db,
                session_id=session_id,
                roi_sha256=roi_sha,
                roi_bytes=roi_bytes,
                metadata=meta,
            )
            resp["donation"]["stored"] = bool(donation_stored)
            resp["donation"]["reason"] = donation_reason

    log_audit(
        db,
        event_type="analyze_completed",
        session_id=session_id,
        request=request,
        payload={
            "roi_sha256": roi_sha or None,
            "model_version": payload.get("model_version"),
            "quality": payload.get("quality"),
            "regions_count": len(payload.get("regions", []) or []),
            "attributes_count": len(payload.get("attributes", []) or []),
            "stored_for_progress": bool(resp["stored_for_progress"]),
            "donation_stored": bool(donation_stored),
            "donation_reason": donation_reason,
        },
    )
    db.commit()

    return resp
