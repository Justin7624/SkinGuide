# services/ml/app/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException, Header
import numpy as np
import cv2

from .quality import blur_level, lighting_level
from .model import model
from .roi import extract_skin_roi, pose_quality_from_landmarks

app = FastAPI(title="SkinGuide ML", version="0.3.0")

REGIONS = ["forehead", "left_cheek", "right_cheek", "nose", "chin"]

def _crop_region(roi_bgr, roi_mask, x1, y1, x2, y2):
    """
    Crops a subregion from roi and applies the skin mask.
    Returns (region_img_bgr, region_mask, skin_pixels)
    """
    h, w = roi_bgr.shape[:2]
    x1 = max(0, min(w - 1, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h - 1, y1))
    y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return None, None, 0

    sub = roi_bgr[y1:y2, x1:x2].copy()
    subm = roi_mask[y1:y2, x1:x2].copy()
    skin_pixels = int(np.sum(subm > 0))

    if skin_pixels <= 300:  # tiny region / mostly excluded pixels
        return None, None, skin_pixels

    sub = cv2.bitwise_and(sub, sub, mask=subm)
    return sub, subm, skin_pixels

def _compute_regions(roi_bgr, roi_mask):
    """
    Region heuristic inside ROI bbox (clinical feel without brittle landmark polygons):
      - Forehead: top ~32%
      - Cheeks: middle band ~32-70% split left/right
      - Nose: center of middle band
      - Chin: bottom ~70-100%
    """
    h, w = roi_bgr.shape[:2]

    y_fore = int(0.32 * h)
    y_mid1 = int(0.32 * h)
    y_mid2 = int(0.70 * h)
    y_chin1 = int(0.70 * h)

    x_mid = int(0.50 * w)

    # Nose window (center)
    nx1 = int(0.35 * w)
    nx2 = int(0.65 * w)
    ny1 = int(0.35 * h)
    ny2 = int(0.65 * h)

    regions = {}

    # Forehead
    regions["forehead"] = (0, 0, w, y_fore)

    # Cheeks (middle band)
    regions["left_cheek"] = (0, y_mid1, x_mid, y_mid2)
    regions["right_cheek"] = (x_mid, y_mid1, w, y_mid2)

    # Nose (center)
    regions["nose"] = (nx1, ny1, nx2, ny2)

    # Chin
    regions["chin"] = (0, y_chin1, w, h)

    out = []
    for name in REGIONS:
        x1, y1, x2, y2 = regions[name]
        img, msk, skin_px = _crop_region(roi_bgr, roi_mask, x1, y1, x2, y2)
        out.append((name, x1, y1, x2 - x1, y2 - y1, img, skin_px))
    return out

def _aggregate_overall(region_results):
    """
    Weighted average of region scores by skin pixel count.
    """
    # region_results: list of dicts with keys: skin_pixels, attributes[{key,score,confidence}]
    totals = {}
    confs = {}
    weight_sum = 0.0

    for rr in region_results:
        w = float(rr.get("skin_pixels", 0))
        attrs = rr.get("attributes") or []
        if w <= 0 or not attrs:
            continue
        weight_sum += w
        for a in attrs:
            k = a["key"]
            totals[k] = totals.get(k, 0.0) + w * float(a["score"])
            confs[k] = confs.get(k, 0.0) + w * float(a["confidence"])

    if weight_sum <= 0:
        return []

    out = []
    for k in sorted(totals.keys()):
        out.append({
            "key": k,
            "score": round(totals[k] / weight_sum, 4),
            "confidence": round(confs[k] / weight_sum, 4),
        })
    return out

@app.post("/infer")
async def infer(
    image: UploadFile = File(...),
    x_return_roi: str | None = Header(default=None),  # set "1" to include ROI jpeg b64
):
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "JPG/PNG only")

    data = await image.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Bad image")

    roi_pack = extract_skin_roi(img)
    if roi_pack is None:
        raise HTTPException(422, "Unable to isolate face/skin ROI. Try better lighting, straight-on angle.")

    roi_bgr, bbox, roi_mask, roi_jpeg_b64, roi_sha = roi_pack

    # Overall quality computed on ROI
    roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    quality = {
        "lighting": lighting_level(roi_gray),
        "blur": blur_level(roi_gray),
        "angle": pose_quality_from_landmarks(img),
        "makeup_suspected": False,  # later
    }

    # Region breakdown
    region_defs = _compute_regions(roi_bgr, roi_mask)
    region_results = []
    for (name, rx, ry, rw, rh, region_img, skin_px) in region_defs:
        if region_img is None:
            region_results.append({
                "name": name,
                "bbox": {"x": rx, "y": ry, "w": rw, "h": rh},
                "skin_pixels": int(skin_px),
                "quality": {"lighting": "low", "blur": "high", "angle": quality["angle"], "makeup_suspected": False},
                "attributes": [],
                "status": "insufficient_skin",
            })
            continue

        g = cv2.cvtColor(region_img, cv2.COLOR_BGR2GRAY)
        rq = {
            "lighting": lighting_level(g),
            "blur": blur_level(g),
            "angle": quality["angle"],
            "makeup_suspected": False,
        }

        attrs = model.infer(region_img)
        region_results.append({
            "name": name,
            "bbox": {"x": rx, "y": ry, "w": rw, "h": rh},
            "skin_pixels": int(skin_px),
            "quality": rq,
            "attributes": attrs,
            "status": "ok",
        })

    # Compute overall from regions (more stable than running once on full ROI)
    attributes_overall = _aggregate_overall(region_results)

    resp = {
        "quality": quality,
        "attributes": attributes_overall,
        "regions": region_results,
        "model_version": model.version,
        "roi_bbox": {"x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]},
        "roi_sha256": roi_sha,
    }

    if x_return_roi == "1":
        resp["roi_jpeg_b64"] = roi_jpeg_b64

    return resp

@app.get("/health")
def health():
    return {"ok": True, "model_version": model.version}
