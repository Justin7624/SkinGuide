# services/ml/app/main.py

import base64
import hashlib
import io

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Header
from fastapi.responses import JSONResponse

from .roi import extract_roi_and_regions  # assumes you already have this
from .model import model

app = FastAPI(title="SkinGuide ML", version="0.5.0")

@app.get("/health")
def health():
    return {"ok": True, "model_version": model.version()}

@app.post("/infer")
async def infer(image: UploadFile = File(...), x_return_roi: str | None = Header(default=None)):
    data = await image.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"error": "bad_image"}, status_code=400)

    roi_bgr, roi_jpeg_bytes, roi_sha256, quality, regions = extract_roi_and_regions(img)
    if roi_bgr is None:
        return JSONResponse({"error": "roi_not_found"}, status_code=422)

    attrs = model.infer_scores(roi_bgr)

    payload = {
        "model_version": model.version(),
        "quality": quality,
        "attributes": attrs,
        "regions": regions,
        "roi_sha256": roi_sha256,
    }

    if x_return_roi:
        payload["roi_jpeg_b64"] = base64.b64encode(roi_jpeg_bytes).decode("ascii")

    return payload
