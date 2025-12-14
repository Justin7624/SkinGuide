from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session as OrmSession
from .db import get_db
from .config import settings
from .security import rate_limit_or_429
from . import models, schemas
import httpx, os, json, uuid

router = APIRouter(prefix="/v1", tags=["analyze"])

DISCLAIMER = "Cosmetic/appearance guidance only. Not a medical diagnosis or medical advice."

def build_plan(attributes, quality):
    s = {a["key"]: a["score"] for a in attributes}
    conservative = quality["lighting"] != "ok" or quality["blur"] == "high" or quality["angle"] != "ok"

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
async def analyze(session_id: str, image: UploadFile = File(...), db: OrmSession = Depends(get_db)):
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

    # Get consent (default: none)
    c = db.get(models.Consent, session_id)
    store_progress = bool(c.store_progress_images) if c else False
    donate = bool(c.donate_for_improvement) if c else False

    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.post(settings.ML_URL, files={"image": data})
    if r.status_code != 200:
        raise HTTPException(502, "Inference service error")
    payload = r.json()

    plan = build_plan(payload["attributes"], payload["quality"])
    resp = {
        "disclaimer": DISCLAIMER,
        "quality": payload["quality"],
        "attributes": payload["attributes"],
        "routine": plan["routine"],
        "professional_to_discuss": plan["pro"],
        "when_to_seek_care": plan["seek_care"],
        "model_version": payload["model_version"],
        "stored_for_progress": False,
    }

    # Store progress ONLY if user opted in AND server storage enabled.
    if store_progress and settings.STORE_IMAGES_ENABLED:
        os.makedirs(settings.IMAGE_STORE_DIR, exist_ok=True)
        fname = f"{uuid.uuid4()}.jpg"
        fpath = os.path.join(settings.IMAGE_STORE_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(data)

        entry = models.ProgressEntry(
            session_id=session_id,
            roi_image_path=fpath,
            result_json=json.dumps(resp)
        )
        db.add(entry)
        db.commit()
        resp["stored_for_progress"] = True

    # Donate for improvement: in MVP we only record a flag in result_json
    # (In production, you’d enqueue to a secure dataset bucket/queue with additional governance.)
    if donate:
        # no-op placeholder; you’d push to a queue here
        pass

    return resp
