# services/ml/app/roi.py

import cv2
import numpy as np
import hashlib
import base64
import mediapipe as mp

from mediapipe.python.solutions.face_mesh_connections import (
    FACEMESH_FACE_OVAL,
    FACEMESH_LIPS,
    FACEMESH_LEFT_EYE,
    FACEMESH_RIGHT_EYE,
)

_mp_face_mesh = mp.solutions.face_mesh

# Reuse one instance for speed
_face_mesh = _mp_face_mesh.FaceMesh(
    static_image_mode=True,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

def _unique_idx_from_connections(connections):
    idx = set()
    for a, b in connections:
        idx.add(a)
        idx.add(b)
    return list(idx)

IDX_FACE_OVAL = _unique_idx_from_connections(FACEMESH_FACE_OVAL)
IDX_LIPS = _unique_idx_from_connections(FACEMESH_LIPS)
IDX_LEFT_EYE = _unique_idx_from_connections(FACEMESH_LEFT_EYE)
IDX_RIGHT_EYE = _unique_idx_from_connections(FACEMESH_RIGHT_EYE)

def _pts(landmarks, idxs, w, h):
    pts = []
    for i in idxs:
        lm = landmarks[i]
        pts.append([int(lm.x * w), int(lm.y * h)])
    return np.array(pts, dtype=np.int32)

def _fill_hull(mask, pts, value):
    if pts is None or len(pts) < 3:
        return
    hull = cv2.convexHull(pts)
    cv2.fillConvexPoly(mask, hull, value)

def _encode_jpeg_b64(img_bgr, quality=85):
    ok, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("Failed to encode ROI jpeg")
    raw = buf.tobytes()
    return base64.b64encode(raw).decode("ascii"), raw

def extract_skin_roi(img_bgr: np.ndarray):
    """
    Extracts a skin-only ROI using MediaPipe Face Mesh:
      - face oval filled
      - subtract eyes + lips
    Returns:
      roi_bgr, bbox(x,y,w,h) in ORIGINAL IMAGE coords, roi_mask (uint8 0/255), roi_jpeg_b64, roi_sha256
    """
    h, w = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    res = _face_mesh.process(img_rgb)
    if not res.multi_face_landmarks:
        return None

    lms = res.multi_face_landmarks[0].landmark

    # Build face-oval mask
    mask = np.zeros((h, w), dtype=np.uint8)
    face_pts = _pts(lms, IDX_FACE_OVAL, w, h)
    _fill_hull(mask, face_pts, 255)

    # Subtract eyes + lips
    lips_pts = _pts(lms, IDX_LIPS, w, h)
    leye_pts = _pts(lms, IDX_LEFT_EYE, w, h)
    reye_pts = _pts(lms, IDX_RIGHT_EYE, w, h)
    _fill_hull(mask, lips_pts, 0)
    _fill_hull(mask, leye_pts, 0)
    _fill_hull(mask, reye_pts, 0)

    # Ensure enough pixels remain
    area = int(np.sum(mask > 0))
    if area < (h * w) * 0.05:
        return None

    # Tight bbox around skin mask
    ys, xs = np.where(mask > 0)
    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())

    # Small padding
    pad_x = int((x2 - x1) * 0.05)
    pad_y = int((y2 - y1) * 0.05)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w - 1, x2 + pad_x)
    y2 = min(h - 1, y2 + pad_y)

    roi = img_bgr[y1:y2, x1:x2].copy()
    roi_mask = mask[y1:y2, x1:x2].copy()

    # Apply mask so non-skin pixels are black
    roi_masked = cv2.bitwise_and(roi, roi, mask=roi_mask)

    roi_b64, roi_raw = _encode_jpeg_b64(roi_masked, quality=85)
    roi_sha = hashlib.sha256(roi_raw).hexdigest()

    return roi_masked, (x1, y1, x2 - x1, y2 - y1), roi_mask, roi_b64, roi_sha

def pose_quality_from_landmarks(img_bgr: np.ndarray) -> str:
    """
    Simple yaw proxy: compare left/right eye bbox areas.
    Returns "ok" or "bad".
    """
    h, w = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    res = _face_mesh.process(img_rgb)
    if not res.multi_face_landmarks:
        return "bad"

    lms = res.multi_face_landmarks[0].landmark
    le = _pts(lms, IDX_LEFT_EYE, w, h)
    re = _pts(lms, IDX_RIGHT_EYE, w, h)

    def bbox_area(pts):
        x, y, bw, bh = cv2.boundingRect(pts)
        return max(1, bw * bh)

    a1 = bbox_area(le)
    a2 = bbox_area(re)
    ratio = max(a1, a2) / max(1, min(a1, a2))

    return "bad" if ratio > 2.2 else "ok"
