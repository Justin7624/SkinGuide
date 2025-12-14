import cv2, numpy as np

def blur_level(gray: np.ndarray) -> str:
    v = cv2.Laplacian(gray, cv2.CV_64F).var()
    if v < 60: return "high"
    if v < 140: return "medium"
    return "low"

def lighting_level(gray: np.ndarray) -> str:
    m = float(np.mean(gray))
    if m < 70: return "low"
    if m > 190: return "harsh"
    return "ok"

def angle_ok(face_bbox) -> str:
    # MVP: if we detect a face, assume ok. (Upgrade later with landmarks/yaw.)
    return "ok" if face_bbox is not None else "bad"
