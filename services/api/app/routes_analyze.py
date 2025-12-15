# services/api/app/routes_analyze.py

from __future__ import annotations

import io
import json
import os
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

import numpy as np
from PIL import Image, ImageOps

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from . import models
from .ml.model_manager import MODEL_MANAGER

try:
    import torch
    from torchvision import transforms
except Exception as e:
    raise RuntimeError(f"torch + torchvision are required for ML inference. Import error: {e}")

router = APIRouter(prefix="/v1/analyze", tags=["analyze"])


class AnalyzeResponse(BaseModel):
    ok: bool = True

    inference_source: str = Field(description="model|heuristics")
    active_model_version: Optional[str] = None
    model_active: bool = False

    deployment: dict = Field(default_factory=dict, description="Stable/canary deployment info (if available)")

    roi: dict = Field(default_factory=dict)
    regions: dict = Field(default_factory=dict)

    global_scores: Dict[str, float] = Field(default_factory=dict)
    region_scores: Dict[str, Dict[str, float]] = Field(default_factory=dict)

    top_concerns: List[dict] = Field(default_factory=list)
    recommendations: List[dict] = Field(default_factory=list)

    disclaimer: str = "This tool provides cosmetic/appearance guidance only and is not a medical diagnosis."


def _now_iso() -> str:
    import datetime
    return datetime.datetime.utcnow().isoformat() + "Z"


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _to_rgb_pil(img: Image.Image) -> Image.Image:
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _load_upload_as_pil(file: UploadFile) -> Image.Image:
    try:
        data = file.file.read()
        if not data:
            raise ValueError("empty file")
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        return _to_rgb_pil(img)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image upload: {e}")


def _pil_to_jpeg_bytes(img: Image.Image, quality: int = 92) -> bytes:
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=int(quality), optimize=True)
    return out.getvalue()


def _clamp01(x: float) -> float:
    if x != x:
        return 0.0
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@dataclass
class ROIResult:
    roi_image: Image.Image
    roi_box_xyxy: Tuple[int, int, int, int]
    face_found: bool
    method: str
    debug: Dict[str, Any]


def _try_import_mediapipe():
    try:
        import mediapipe as mp  # type: ignore
        return mp
    except Exception:
        return None


def _extract_roi(img: Image.Image) -> ROIResult:
    w, h = img.size
    mp = _try_import_mediapipe()

    if mp is not None:
        try:
            import cv2  # type: ignore

            np_img = np.array(img)[:, :, ::-1]
            mp_face = mp.solutions.face_detection
            with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as fd:
                res = fd.process(np_img)
                if res.detections:
                    det = sorted(res.detections, key=lambda d: d.score[0], reverse=True)[0]
                    box = det.location_data.relative_bounding_box
                    x1 = int(max(0, box.xmin * w))
                    y1 = int(max(0, box.ymin * h))
                    x2 = int(min(w, (box.xmin + box.width) * w))
                    y2 = int(min(h, (box.ymin + box.height) * h))

                    bw = x2 - x1
                    bh = y2 - y1
                    pad_x = int(bw * 0.20)
                    pad_y_top = int(bh * 0.35)
                    pad_y_bot = int(bh * 0.20)

                    ex1 = max(0, x1 - pad_x)
                    ey1 = max(0, y1 - pad_y_top)
                    ex2 = min(w, x2 + pad_x)
                    ey2 = min(h, y2 + pad_y_bot)

                    roi = img.crop((ex1, ey1, ex2, ey2))
                    return ROIResult(
                        roi_image=roi,
                        roi_box_xyxy=(ex1, ey1, ex2, ey2),
                        face_found=True,
                        method="mediapipe_face_detection",
                        debug={"score": float(det.score[0])},
                    )
        except Exception:
            pass

    crop_w = int(w * 0.70)
    crop_h = int(h * 0.70)
    cx = w // 2
    cy = int(h * 0.42)
    x1 = max(0, cx - crop_w // 2)
    y1 = max(0, cy - crop_h // 2)
    x2 = min(w, x1 + crop_w)
    y2 = min(h, y1 + crop_h)
    roi = img.crop((x1, y1, x2, y2))

    return ROIResult(
        roi_image=roi,
        roi_box_xyxy=(x1, y1, x2, y2),
        face_found=False,
        method="center_crop_fallback",
        debug={},
    )


def _compute_regions(roi: ROIResult) -> Dict[str, Any]:
    rw, rh = roi.roi_image.size

    def rect(px1, py1, px2, py2):
        return {
            "x1": int(px1 * rw),
            "y1": int(py1 * rh),
            "x2": int(px2 * rw),
            "y2": int(py2 * rh),
        }

    regions = {
        "forehead": rect(0.20, 0.02, 0.80, 0.28),
        "left_cheek": rect(0.06, 0.34, 0.42, 0.70),
        "right_cheek": rect(0.58, 0.34, 0.94, 0.70),
        "nose": rect(0.40, 0.28, 0.60, 0.60),
        "chin": rect(0.30, 0.70, 0.70, 0.96),
        "under_eye_left": rect(0.12, 0.26, 0.42, 0.40),
        "under_eye_right": rect(0.58, 0.26, 0.88, 0.40),
    }

    return {
        "roi_size": {"w": rw, "h": rh},
        "regions": regions,
        "method": "percent_rects",
    }


def _heuristic_scores_from_roi(roi_img: Image.Image) -> Dict[str, float]:
    img = _to_rgb_pil(roi_img).resize((256, 256))
    a = np.asarray(img).astype(np.float32) / 255.0

    r = a[:, :, 0]
    g = a[:, :, 1]
    b = a[:, :, 2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

    lap = (
        -4 * lum
        + np.roll(lum, 1, axis=0)
        + np.roll(lum, -1, axis=0)
        + np.roll(lum, 1, axis=1)
        + np.roll(lum, -1, axis=1)
    )
    texture = float(np.var(lap))
    texture_score = _clamp01((texture - 0.0003) / (0.0020 - 0.0003 + 1e-9))

    redness = float(np.mean(np.clip(r - g, 0, 1)))
    redness_score = _clamp01((redness - 0.02) / (0.10 - 0.02 + 1e-9))

    chroma = np.sqrt((r - g) ** 2 + (g - b) ** 2 + (b - r) ** 2)
    chroma_var = float(np.var(chroma))
    pigment_score = _clamp01((chroma_var - 0.002) / (0.020 - 0.002 + 1e-9))

    highlights = float(np.mean(lum > 0.85))
    oil_score = _clamp01((highlights - 0.02) / (0.18 - 0.02 + 1e-9))

    lower = lum[int(256 * 0.30): int(256 * 0.55), :]
    under_eye_dark = float(1.0 - np.mean(lower))
    under_eye_score = _clamp01((under_eye_dark - 0.35) / (0.60 - 0.35 + 1e-9))

    return {
        "g:hyperpigmentation": pigment_score,
        "g:redness": redness_score,
        "g:texture": texture_score,
        "g:oiliness": oil_score,
        "g:under_eye_darkness": under_eye_score,
        "g:acne_prone": _clamp01((oil_score * 0.6) + (texture_score * 0.4)),
        "g:photoaging": _clamp01((pigment_score * 0.55) + (texture_score * 0.45)),
    }


def _split_predictions(pred: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    global_scores: Dict[str, float] = {}
    region_scores: Dict[str, Dict[str, float]] = {}

    for k, v in pred.items():
        if k.startswith("g:"):
            global_scores[k[2:]] = float(v)
        elif k.startswith("r:"):
            parts = k.split(":", 2)
            if len(parts) == 3:
                region = parts[1]
                attr = parts[2]
                region_scores.setdefault(region, {})[attr] = float(v)

    global_scores = dict(sorted(global_scores.items(), key=lambda kv: kv[0]))
    for r in list(region_scores.keys()):
        region_scores[r] = dict(sorted(region_scores[r].items(), key=lambda kv: kv[0]))
    region_scores = dict(sorted(region_scores.items(), key=lambda kv: kv[0]))
    return global_scores, region_scores


def _topk(scores: Dict[str, float], k: int = 5, min_score: float = 0.25) -> List[Tuple[str, float]]:
    items = [(a, float(s)) for a, s in scores.items()]
    items.sort(key=lambda x: x[1], reverse=True)
    items = [(a, s) for a, s in items if s >= float(min_score)]
    return items[: int(k)]


def _recommendations_from_scores(global_scores: Dict[str, float]) -> Tuple[List[dict], List[dict]]:
    concerns = _topk(global_scores, k=6, min_score=0.25)
    top_concerns = [{"concern": c, "score": round(s, 4)} for c, s in concerns]

    recs: List[dict] = []
    if any(c in ("hyperpigmentation", "photoaging") for c, _ in concerns):
        recs.append({
            "category": "Daily routine",
            "title": "Broad-spectrum sunscreen (SPF 30+)",
            "why": "UV protection helps prevent dark spots and visible photoaging.",
            "options": ["SPF 30+", "SPF 50+", "tinted mineral SPF if prone to pigmentation"],
        })
        recs.append({
            "category": "Actives",
            "title": "Vitamin C (AM) + retinoid (PM, slowly)",
            "why": "Common cosmetic-grade approach for tone + texture over time.",
            "options": ["L-ascorbic acid or derivatives", "retinal/retinol", "rx retinoid via clinician if appropriate"],
        })
        recs.append({
            "category": "In-office (clinician)",
            "title": "Laser/IPL or RF microneedling consult",
            "why": "Procedures may address spots and texture depending on skin type and diagnosis.",
            "options": ["IPL (select cases)", "fractional laser (select cases)", "RF microneedling"],
        })

    if any(c in ("acne_prone", "oiliness") for c, _ in concerns):
        recs.append({
            "category": "Routine",
            "title": "Gentle cleanser + non-comedogenic moisturizer",
            "why": "Helps manage oil without over-stripping.",
            "options": ["gentle foaming cleanser", "light gel moisturizer"],
        })
        recs.append({
            "category": "Actives",
            "title": "BHA / benzoyl peroxide (spot or wash) as tolerated",
            "why": "Common cosmetic/OTC options for acne-prone skin. Patch test first.",
            "options": ["salicylic acid (BHA)", "benzoyl peroxide wash", "azelaic acid"],
        })
        recs.append({
            "category": "Clinician",
            "title": "If persistent: dermatology evaluation",
            "why": "Acne, folliculitis, or dermatitis can look similar and may need diagnosis.",
            "options": ["topicals", "oral meds if indicated", "rule out fungal folliculitis"],
        })

    if any(c in ("redness",) for c, _ in concerns):
        recs.append({
            "category": "Barrier",
            "title": "Barrier support + fragrance-free routine",
            "why": "Redness can be worsened by irritation; simplify routine first.",
            "options": ["ceramide moisturizer", "gentle cleanser", "avoid harsh scrubs"],
        })
        recs.append({
            "category": "Clinician",
            "title": "Consider evaluation for rosacea/dermatitis triggers",
            "why": "Persistent redness may benefit from a clinician’s assessment.",
            "options": ["trigger review", "topicals if diagnosed", "vascular laser consult"],
        })

    if any(c in ("under_eye_darkness",) for c, _ in concerns):
        recs.append({
            "category": "Under-eye",
            "title": "Hydration + sun protection + sleep consistency",
            "why": "Under-eye appearance is influenced by hydration, shadowing, and sun exposure.",
            "options": ["hydrating eye gel", "tinted SPF", "consider clinician for pigment vs vascular"],
        })

    if not recs:
        recs.append({
            "category": "Baseline",
            "title": "Simple routine first",
            "why": "Start with cleanser + moisturizer + SPF, then add one active at a time.",
            "options": ["gentle cleanser", "moisturizer", "SPF"],
        })

    return top_concerns, recs


def _get_or_create_session(db: OrmSession, request: Request) -> models.Session:
    sid = request.headers.get("X-Session-Id")
    if sid:
        s = db.get(models.Session, sid)
        if s:
            return s

    import uuid
    sid = str(uuid.uuid4())
    s = models.Session(id=sid)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _get_consent(db: OrmSession, session_id: str) -> Optional[models.Consent]:
    return db.get(models.Consent, session_id)


@router.post("", response_model=AnalyzeResponse)
async def analyze_face(
    request: Request,
    image: UploadFile = File(...),
    db: OrmSession = Depends(get_db),
):
    session = _get_or_create_session(db, request)
    consent = _get_consent(db, session.id)

    pil = _load_upload_as_pil(image)

    roi = _extract_roi(pil)
    roi_img = roi.roi_image
    roi_jpeg = _pil_to_jpeg_bytes(roi_img)
    roi_sha = _sha256_bytes(roi_jpeg)

    regions = _compute_regions(roi)

    inference_source = "heuristics"
    model_version_used: Optional[str] = None
    model_active = False
    deployment_info: Dict[str, Any] = {}

    global_scores: Dict[str, float] = {}
    region_scores: Dict[str, Dict[str, float]] = {}

    # Attempt model inference (stable/canary selected by session hash)
    try:
        snap = MODEL_MANAGER.ensure_current()
        deployment_info = dict(snap)

        # If no stable model exists, choose_version_for_session returns None and we fall back
        chosen = MODEL_MANAGER.choose_version_for_session(session.id)
        if chosen:
            # Build tensor to match the chosen model's image size:
            # ModelManager exposes size via predict_tensor_for_session info; we can do a quick call
            # BUT we must preprocess before calling. We'll use stable size if loaded, else 224.
            # Safer: use manager.active_info to pick stable/canary loaded size if available.
            info = MODEL_MANAGER.active_info()
            # select size based on whether chosen is canary or stable (loaded)
            img_size = 224
            if info.get("stable") and info["stable"].get("version") == chosen:
                img_size = int(info["stable"].get("image_size") or 224)
            elif info.get("canary") and info["canary"].get("version") == chosen:
                img_size = int(info["canary"].get("image_size") or 224)
            else:
                # fallback
                img_size = 224

            tf = transforms.Compose([
                transforms.Resize((img_size, img_size)),
                transforms.ToTensor(),
            ])
            x = tf(_to_rgb_pil(roi_img)).unsqueeze(0)

            pred, inf = MODEL_MANAGER.predict_tensor_for_session(session.id, x)
            model_version_used = inf.get("version_used")
            model_active = True
            inference_source = "model"

            # include richer deployment info
            deployment_info = {
                "stable_version": inf.get("stable_version"),
                "canary_version": inf.get("canary_version"),
                "canary_percent": inf.get("canary_percent"),
                "deployment_enabled": inf.get("deployment_enabled"),
                "version_used": inf.get("version_used"),
            }

            global_scores, region_scores = _split_predictions(pred)
        else:
            hs = _heuristic_scores_from_roi(roi_img)
            global_scores, region_scores = _split_predictions(hs)

    except Exception:
        # Any model errors => heuristics
        hs = _heuristic_scores_from_roi(roi_img)
        global_scores, region_scores = _split_predictions(hs)
        inference_source = "heuristics"
        model_version_used = None
        model_active = False

    top_concerns, recs = _recommendations_from_scores(global_scores)

    # Optional persistence
    try:
        result_payload = {
            "ts": _now_iso(),
            "inference_source": inference_source,
            "active_model_version": model_version_used,
            "model_active": model_active,
            "deployment": deployment_info,
            "roi": {
                "face_found": roi.face_found,
                "method": roi.method,
                "roi_box_xyxy": roi.roi_box_xyxy,
                "roi_sha256": roi_sha,
            },
            "regions": regions,
            "global_scores": global_scores,
            "region_scores": region_scores,
            "top_concerns": top_concerns,
            "recommendations": recs,
        }

        if consent and consent.store_progress_images:
            base_dir = os.environ.get("UPLOAD_DIR", "uploads")
            out_dir = os.path.join(base_dir, "progress", session.id)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{roi_sha}.jpg")
            if not os.path.exists(out_path):
                with open(out_path, "wb") as f:
                    f.write(roi_jpeg)

            pe = models.ProgressEntry(
                session_id=session.id,
                roi_image_path=out_path,
                result_json=_safe_json_dumps(result_payload),
            )
            db.add(pe)
            db.commit()

        if consent and consent.donate_for_improvement:
            existing = (
                db.query(models.DonatedSample)
                .filter(models.DonatedSample.roi_sha256 == roi_sha)
                .first()
            )
            if not existing:
                base_dir = os.environ.get("UPLOAD_DIR", "uploads")
                out_dir = os.path.join(base_dir, "donations")
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, f"{roi_sha}.jpg")
                if not os.path.exists(out_path):
                    with open(out_path, "wb") as f:
                        f.write(roi_jpeg)

                meta = {
                    "session_id": session.id,
                    "roi_box_xyxy": roi.roi_box_xyxy,
                    "roi_method": roi.method,
                    "face_found": roi.face_found,
                    "regions": regions,
                    "img_size": {"w": pil.size[0], "h": pil.size[1]},
                }

                ds = models.DonatedSample(
                    session_id=session.id,
                    roi_sha256=roi_sha,
                    roi_image_path=out_path,
                    metadata_json=_safe_json_dumps(meta),
                )
                db.add(ds)
                db.commit()

    except Exception:
        pass

    return AnalyzeResponse(
        ok=True,
        inference_source=inference_source,
        active_model_version=model_version_used,  # always present when model is used
        model_active=model_active,
        deployment=deployment_info,
        roi={
            "face_found": roi.face_found,
            "method": roi.method,
            "roi_box_xyxy": roi.roi_box_xyxy,
            "roi_sha256": roi_sha,
        },
        regions=regions,
        global_scores=global_scores,
        region_scores=region_scores,
        top_concerns=top_concerns,
        recommendations=recs,
        disclaimer="This tool provides cosmetic/appearance guidance only and is not a medical diagnosis. For persistent or concerning skin issues, consult a licensed clinician.",
    )
