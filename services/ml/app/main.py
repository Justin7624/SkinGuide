from fastapi import FastAPI, UploadFile, File, HTTPException
import numpy as np, cv2
from .quality import blur_level, lighting_level, angle_ok
from .model import model

app = FastAPI(title="SkinGuide ML", version="0.1.0")

FACE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

@app.post("/infer")
async def infer(image: UploadFile = File(...)):
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "JPG/PNG only")

    data = await image.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Bad image")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = FACE.detectMultiScale(gray, 1.1, 5, minSize=(120, 120))
    face_bbox = faces[0] if len(faces) else None

    quality = {
        "lighting": lighting_level(gray),
        "blur": blur_level(gray),
        "angle": angle_ok(face_bbox),
        "makeup_suspected": False,  # placeholder (hard problem; do later)
    }

    attributes = model.infer(img)
    return {"quality": quality, "attributes": attributes, "model_version": model.version}

@app.get("/health")
def health():
    return {"ok": True, "model_version": model.version}
