# services/api/app/ml/model_manager.py

from __future__ import annotations

import json
import os
import threading
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple

import torch
import torch.nn as nn

from sqlalchemy.orm import Session as OrmSession

from .. import models
from ..db import SessionLocal
from ..storage import get_storage

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


def _loads_json(s: str) -> dict:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _read_text_local(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _ensure_local(uri: str) -> Optional[str]:
    if not uri:
        return None
    if uri.startswith("s3://"):
        storage = get_storage()
        return storage.get_local_path_if_any(uri)
    return uri


def _load_manifest(manifest_uri: str) -> dict:
    lp = _ensure_local(manifest_uri)
    if not lp or not os.path.exists(lp):
        raise RuntimeError(f"Manifest not accessible locally: {manifest_uri}")
    return _loads_json(_read_text_local(lp))


def _build_model(out_dim: int) -> nn.Module:
    m = resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, out_dim)
    return m


def _session_bucket(session_id: str, salt: str) -> int:
    s = (session_id or "") + "|" + (salt or "")
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


class ModelManager:
    """
    Loads stable + (optional) canary model for staged rollout.
    Stable = ModelArtifact where is_active=True
    Canary = ModelDeployment.canary_model_id if enabled and canary_percent>0
    """

    def __init__(self, *, check_interval_sec: float = 10.0, device: Optional[str] = None):
        self.check_interval_sec = float(check_interval_sec)
        self.device = torch.device(device) if device else torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.salt = os.environ.get("CANARY_ROLLOUT_SALT", "skinguide-default-salt")

        self._lock = threading.RLock()
        self._last_check = 0.0

        # cached loaded models
        self._stable: Optional[LoadedModel] = None
        self._canary: Optional[LoadedModel] = None

        # cached deployment config snapshot
        self._deploy: Dict[str, Any] = {
            "enabled": False,
            "canary_percent": 0,
            "canary_version": None,
            "stable_version": None,
        }

    def _db_get_active_stable(self, db: OrmSession) -> Optional[models.ModelArtifact]:
        return (
            db.query(models.ModelArtifact)
            .filter(models.ModelArtifact.is_active == True)  # noqa: E712
            .order_by(models.ModelArtifact.created_at.desc())
            .first()
        )

    def _db_get_deployment(self, db: OrmSession) -> Optional[models.ModelDeployment]:
        return db.query(models.ModelDeployment).order_by(models.ModelDeployment.id.asc()).first()

    def ensure_current(self) -> Dict[str, Any]:
        """
        Refresh stable/canary model cache if needed.
        Returns deployment snapshot including versions.
        """
        now = time.time()
        with self._lock:
            if (now - self._last_check) < self.check_interval_sec:
                return dict(self._deploy)
            self._last_check = now

        db = SessionLocal()
        try:
            stable_art = self._db_get_active_stable(db)
            dep = self._db_get_deployment(db)

            stable_version = stable_art.version if stable_art else None

            dep_enabled = bool(dep.enabled) if dep else False
            canary_percent = int(dep.canary_percent) if dep else 0
            canary_art = None
            if dep and dep_enabled and canary_percent > 0 and dep.canary_model_id:
                canary_art = db.get(models.ModelArtifact, int(dep.canary_model_id))

            canary_version = canary_art.version if canary_art else None

            # load stable if changed
            if stable_art:
                with self._lock:
                    cur_stable = self._stable.version if self._stable else None
                if cur_stable != stable_version:
                    loaded = self._load_from_artifact(stable_art)
                    with self._lock:
                        self._stable = loaded

            else:
                with self._lock:
                    self._stable = None

            # load canary if changed / disabled
            if canary_art:
                with self._lock:
                    cur_canary = self._canary.version if self._canary else None
                if cur_canary != canary_version:
                    loaded = self._load_from_artifact(canary_art)
                    with self._lock:
                        self._canary = loaded
            else:
                with self._lock:
                    self._canary = None

            snap = {
                "enabled": bool(dep_enabled),
                "canary_percent": int(canary_percent),
                "stable_version": stable_version,
                "canary_version": canary_version,
            }
            with self._lock:
                self._deploy = dict(snap)
            return dict(snap)
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
            label_keys=[str(k) for k in label_keys],
            image_size=image_size,
            model=model,
        )

    def choose_version_for_session(self, session_id: str) -> str | None:
        snap = self.ensure_current()
        stable_v = snap.get("stable_version")
        canary_v = snap.get("canary_version")
        if not stable_v:
            return None

        if snap.get("enabled") and canary_v and int(snap.get("canary_percent") or 0) > 0:
            b = _session_bucket(session_id, self.salt)
            if b < int(snap["canary_percent"]):
                return canary_v
        return stable_v

    def _get_loaded_by_version(self, version: str) -> Optional[LoadedModel]:
        with self._lock:
            if self._stable and self._stable.version == version:
                return self._stable
            if self._canary and self._canary.version == version:
                return self._canary
            return None

    @torch.no_grad()
    def predict_tensor_for_session(self, session_id: str, x: torch.Tensor) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """
        Returns (pred_dict, info)
        info includes: version_used, stable_version, canary_version, canary_percent
        """
        snap = self.ensure_current()
        version = self.choose_version_for_session(session_id)
        if not version:
            raise RuntimeError("No stable active model")

        loaded = self._get_loaded_by_version(version)
        if not loaded:
            # rare race: force refresh and retry
            self.ensure_current()
            loaded = self._get_loaded_by_version(version)
        if not loaded:
            raise RuntimeError("Chosen model not loaded")

        x = x.to(self.device)
        y = loaded.model(x).detach().float().cpu().view(-1).tolist()

        out: Dict[str, float] = {}
        for k, v in zip(loaded.label_keys, y):
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
            out[k] = fv

        info = {
            "version_used": loaded.version,
            "stable_version": snap.get("stable_version"),
            "canary_version": snap.get("canary_version"),
            "canary_percent": int(snap.get("canary_percent") or 0),
            "deployment_enabled": bool(snap.get("enabled")),
            "image_size": loaded.image_size,
            "n_outputs": len(loaded.label_keys),
            "device": str(self.device),
        }
        return out, info

    def active_info(self) -> Dict[str, Any]:
        snap = self.ensure_current()
        with self._lock:
            stable = self._stable
            canary = self._canary
        return {
            "deployment": dict(snap),
            "stable_loaded": bool(stable),
            "canary_loaded": bool(canary),
            "stable": {
                "version": stable.version,
                "image_size": stable.image_size,
                "n_outputs": len(stable.label_keys),
            } if stable else None,
            "canary": {
                "version": canary.version,
                "image_size": canary.image_size,
                "n_outputs": len(canary.label_keys),
            } if canary else None,
            "device": str(self.device),
        }


MODEL_MANAGER = ModelManager(check_interval_sec=float(os.environ.get("MODEL_CHECK_INTERVAL_SEC", "10")))
