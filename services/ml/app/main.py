from fastapi import FastAPI, UploadFile, File, HTTPException, Header
import numpy as np, cv2
from .quality import blur_level, lighting_level
from .model import model
from .roi import extract_skin_roi, pose_quality_from_landmarks

app = FastAPI(title="SkinGuide ML", version="0.2.0")

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

    # Extract skin ROI (face oval minus eyes/lips)
    roi_pack = extract_skin_roi(img)
    if roi_pack is None:
        raise HTTPException(422, "Unable to isolate face/skin ROI. Try better lighting, straight-on angle.")

    roi_bgr, bbox, roi_jpeg_b64, roi_sha = roi_pack

    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

    quality = {
        "lighting": lighting_level(gray),
        "blur": blur_level(gray),
        "angle": pose_quality_from_landmarks(img),
        "makeup_suspected": False,  # later (heuristics + ML)
    }

    # Infer attributes using ROI only
    attributes = model.infer(roi_bgr)

    resp = {
        "quality": quality,
        "attributes": attributes,
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
