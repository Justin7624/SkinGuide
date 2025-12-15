# services/ml/app/model.py

import json
import os
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np
import torch

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

MODEL_PATH = os.getenv("TORCH_MODEL_PATH", "/models/current/model.pt")
VERSION_JSON = os.getenv("MODEL_VERSION_JSON", "/models/current/current_version.json")
FALLBACK_VERSION = os.getenv("MODEL_VERSION", "0.1.0-mvp")

class HotReloadModel:
    def __init__(self):
        self._lock = threading.RLock()
        self._torch_model = None
        self._mtime: float = -1.0
        self._version = FALLBACK_VERSION

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

        # initial load attempt
        self._maybe_reload()

    def _read_version(self) -> str:
        try:
            with open(VERSION_JSON, "r", encoding="utf-8") as f:
                j = json.load(f)
            v = j.get("version")
            return str(v) if v else FALLBACK_VERSION
        except Exception:
            return FALLBACK_VERSION

    def _maybe_reload(self):
        try:
            st = os.stat(MODEL_PATH)
            mtime = float(st.st_mtime)
        except FileNotFoundError:
            return

        with self._lock:
            if mtime == self._mtime:
                return

            try:
                m = torch.jit.load(MODEL_PATH, map_location="cpu")
                m.eval()
            except Exception:
                # keep old model if load fails
                return

            self._torch_model = m
            self._mtime = mtime
            self._version = self._read_version()

    def _watch_loop(self):
        while not self._stop.is_set():
            self._maybe_reload()
            time.sleep(1.0)

    def shutdown(self):
        self._stop.set()
        try:
            self._thread.join(timeout=2.0)
        except Exception:
            pass

    def version(self) -> str:
        with self._lock:
            return self._version

    def _preprocess(self, img_bgr, size=128):
        img = cv2.resize(img_bgr, (size, size), interpolation=cv2.INTER_AREA)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        x = img.astype(np.float32) / 255.0
        x = np.transpose(x, (2, 0, 1))
        x = np.expand_dims(x, 0)
        return torch.from_numpy(x)

    def infer_scores(self, img_bgr) -> list[dict]:
        with self._lock:
            model = self._torch_model
            version = self._version

        if model is None:
            return [{"key": k, "score": 0.5, "confidence": 0.35} for k in ATTRIBUTE_KEYS]

        with torch.no_grad():
            x = self._preprocess(img_bgr)
            logits = model(x)
            scores = torch.sigmoid(logits).cpu().numpy().reshape(-1)

        out = []
        for i, k in enumerate(ATTRIBUTE_KEYS):
            s = float(np.clip(scores[i], 0.0, 1.0))
            out.append({"key": k, "score": round(s, 4), "confidence": 0.6})
        return out

model = HotReloadModel()
