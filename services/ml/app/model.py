# services/ml/app/model.py

import os
import torch
import numpy as np
import cv2

ATTRIBUTE_KEYS = [
    "uneven_tone_appearance",
    "hyperpigmentation_appearance",
    "redness_appearance",
    "texture_roughness_appearance",
    "shine_oiliness_appearance",
    "pore_visibility_appearance",
    "fine_lines_appearance",
    "dryness_flaking_appearance",
]

class InferenceModel:
    def __init__(self):
        self.version = os.getenv("MODEL_VERSION", "0.1.0-mvp")
        self.path = os.getenv("TORCH_MODEL_PATH", "")
        self.torch_model = None
        if self.path and os.path.exists(self.path):
            try:
                self.torch_model = torch.jit.load(self.path, map_location="cpu")
                self.torch_model.eval()
            except Exception:
                self.torch_model = None

    def _preprocess(self, img_bgr):
        img = cv2.resize(img_bgr, (128, 128), interpolation=cv2.INTER_AREA)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        x = img.astype(np.float32) / 255.0
        x = np.transpose(x, (2, 0, 1))  # CHW
        x = np.expand_dims(x, 0)        # NCHW
        return torch.from_numpy(x)

    def infer(self, img_bgr):
        if self.torch_model is None:
            # Fallback: neutral-ish outputs when no trained model is present
            out = []
            for k in ATTRIBUTE_KEYS:
                out.append({"key": k, "score": 0.5, "confidence": 0.4})
            return out

        with torch.no_grad():
            x = self._preprocess(img_bgr)
            logits = self.torch_model(x)
            scores = torch.sigmoid(logits).cpu().numpy().reshape(-1)

        out = []
        for i, k in enumerate(ATTRIBUTE_KEYS):
            s = float(np.clip(scores[i], 0.0, 1.0))
            # confidence placeholder (later: quality- & calibration-based)
            conf = 0.6
            out.append({"key": k, "score": round(s, 4), "confidence": round(conf, 4)})
        return out

model = InferenceModel()
