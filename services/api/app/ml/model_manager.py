# services/api/app/ml/model_manager.py

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

import torch
import torch.nn as nn

from sqlalchemy.orm import Session as OrmSession

from .. import models
from ..db import SessionLocal  # assume your db.py exposes SessionLocal; if not, update import accordingly
from ..storage import get_storage


# ---- minimal resnet18 head (must match trainer) ----
try:
    from torchvision.models import resnet18
except Exception as e:
    raise RuntimeError(f"torchvision is required for inference. Import error: {e}")


@dataclass
class LoadedModel:
    version: str
    model_uri: str
    manifest_uri: str
    label_keys: List[str]
    image_size: int
    model: nn.Module


def _loads(s: str) -> dict:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _read_text_local(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_bytes_local(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _ensure_local(uri: str) -> Optional[str]:
    """
    Supports:
      - local filesystem path
      - storage.get_local_path_if_any(uri) if uri is s3://...
    """
    if not uri:
        return None
    if uri.startswith("s3://"):
        storage = get_storage()
        lp = storage.get_local_path_if_any(uri)
        return lp
    return uri


def _load_manifest(manifest_uri: str) -> dict:
    lp = _ensure_local(manifest_uri)
    if not lp or not os.path.exists(lp):
        raise RuntimeError(f"Manifest not accessible locally: {manifest_uri}")
    return _loads(_read_text_local(lp))


def _build_model(out_dim: int) -> nn.Module:
    m = resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, out_dim)
    return m


class ModelManager:
    """
    Hot reload strategy:
      - cache active model for CHECK_INTERVAL_SEC
      - periodically query DB for active version
      - if changed, load and swap atomically
    """
    def __init__(self, *, check_interval_sec: float = 10.0, device: Optional[str] = None):
        self.check_interval_sec = float(check_interval_sec)
        self.device = torch.device(device) if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self._lock = threading.RLock()
        self._loaded: Optional[LoadedModel] = None
        self._last_check = 0.0

    def _db_get_active(self, db: OrmSession) -> Optional[models.ModelArtifact]:
        return (
            db.query(models.ModelArtifact)
            .filter(models.ModelArtifact.is_active == True)  # noqa: E712
            .order_by(models.ModelArtifact.created_at.desc())
            .first()
        )

    def ensure_current(self) -> Optional[str]:
        """
        Ensures model matches DB active.
        Returns active version or None if no active model.
        """
        now = time.time()
        with self._lock:
            if (now - self._last_check) < self.check_interval_sec:
                return self._loaded.version if self._loaded else None
            self._last_check = now

        db = SessionLocal()
        try:
            active = self._db_get_active(db)
            if not active:
                with self._lock:
                    self._loaded = None
                return None

            active_version = active.version
            with self._lock:
                cur = self._loaded.version if self._loaded else None
            if cur == active_version:
                return active_version

            # reload
            loaded = self._load_from_artifact(active)
            with self._lock:
                self._loaded = loaded
            return active_version
        finally:
            db.close()

    def _load_from_artifact(self, art: models.ModelArtifact) -> LoadedModel:
        manifest = _load_manifest(art.manifest_uri)
        label_keys = manifest.get("label_keys") or []
        image_size = int(manifest.get("image_size") or 224)
        if not isinstance(label_keys, list) or not label_keys:
            raise RuntimeError("Manifest missing label_keys; cannot load model")

        out_dim = len(label_keys)
        model = _build_model(out_dim)
        model_lp = _ensure_local(art.model_uri)
        if not model_lp or not os.path.exists(model_lp):
            raise RuntimeError(f"Model weights not accessible locally: {art.model_uri}")

        state = torch.load(model_lp, map_location="cpu")
        model.load_state_dict(state, strict=True)
        model.eval()
        model.to(self.device)

        return LoadedModel(
            version=art.version,
            model_uri=art.model_uri,
            manifest_uri=art.manifest_uri,
            label_keys=label_keys,
            image_size=image_size,
            model=model,
        )

    @torch.no_grad()
    def predict_tensor(self, x: torch.Tensor) -> Dict[str, float]:
        """
        x: [1,3,H,W] float32 0..1 resized to manifest image_size
        returns dict mapping label key -> float (clamped 0..1)
        """
        self.ensure_current()
        with self._lock:
            if not self._loaded:
                raise RuntimeError("No active model")
            m = self._loaded.model
            keys = self._loaded.label_keys

        x = x.to(self.device)
        y = m(x).detach().float().cpu().view(-1).tolist()
        out: Dict[str, float] = {}
        for k, v in zip(keys, y):
            try:
                fv = float(v)
            except Exception:
                continue
            if fv != fv:
                continue
            if fv < 0.0:
                fv = 0.0
            if fv > 1.0:
                fv = 1.0
            out[str(k)] = fv
        return out

    def active_info(self) -> Dict[str, Any]:
        self.ensure_current()
        with self._lock:
            if not self._loaded:
                return {"active": False}
            return {
                "active": True,
                "version": self._loaded.version,
                "model_uri": self._loaded.model_uri,
                "manifest_uri": self._loaded.manifest_uri,
                "image_size": self._loaded.image_size,
                "n_outputs": len(self._loaded.label_keys),
            }


# singleton
MODEL_MANAGER = ModelManager(check_interval_sec=float(os.environ.get("MODEL_CHECK_INTERVAL_SEC", "10")))
