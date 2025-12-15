# services/api/app/routes_model.py

import json
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import desc

from .db import get_db
from .config import settings
from .security import require_admin
from . import models, schemas
from .storage import get_storage

router = APIRouter(prefix="/v1/model", tags=["model"])

def _ensure_shared_dir():
    os.makedirs(settings.MODEL_SHARED_DIR, exist_ok=True)

def _copy_from_local(src_path: str, dst_path: str):
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copyfile(src_path, dst_path)

@router.get("/current", response_model=schemas.ModelInfo | None)
def current_model(db: OrmSession = Depends(get_db)):
    m = db.query(models.ModelArtifact).filter(models.ModelArtifact.is_active == True).first()  # noqa: E712
    if not m:
        return None
    return schemas.ModelInfo(
        version=m.version,
        model_uri=m.model_uri,
        manifest_uri=m.manifest_uri,
        is_active=m.is_active,
        created_at=m.created_at.isoformat(),
    )

@router.get("/list", response_model=list[schemas.ModelInfo])
def list_models(db: OrmSession = Depends(get_db)):
    ms = db.query(models.ModelArtifact).order_by(desc(models.ModelArtifact.created_at)).all()
    out = []
    for m in ms:
        out.append(schemas.ModelInfo(
            version=m.version,
            model_uri=m.model_uri,
            manifest_uri=m.manifest_uri,
            is_active=m.is_active,
            created_at=m.created_at.isoformat(),
        ))
    return out

@router.post("/register", dependencies=[Depends(require_admin)], response_model=schemas.ModelActivateResponse)
def register_model(req: schemas.ModelRegisterRequest, db: OrmSession = Depends(get_db)):
    exists = db.query(models.ModelArtifact).filter(models.ModelArtifact.version == req.version).first()
    if exists:
        return schemas.ModelActivateResponse(ok=False, reason="version_exists", active_version=None)

    rec = models.ModelArtifact(
        version=req.version,
        model_uri=req.model_uri,
        manifest_uri=req.manifest_uri,
        metrics_json=req.metrics_json,
        is_active=False,
    )
    db.add(rec)
    db.commit()
    return schemas.ModelActivateResponse(ok=True, active_version=None, reason="registered")

@router.post("/activate", dependencies=[Depends(require_admin)], response_model=schemas.ModelActivateResponse)
def activate_model(req: schemas.ModelActivateRequest, db: OrmSession = Depends(get_db)):
    target = db.query(models.ModelArtifact).filter(models.ModelArtifact.version == req.version).first()
    if not target:
        return schemas.ModelActivateResponse(ok=False, reason="not_found", active_version=None)

    # For launch-hardening MVP: activation requires local access to the model files
    # (file:// URIs) so we can place them in the shared /models/current dir for ML container.
    storage = get_storage()
    model_local = storage.get_local_path_if_any(target.model_uri)
    manifest_local = storage.get_local_path_if_any(target.manifest_uri)

    if not model_local or not os.path.exists(model_local):
        return schemas.ModelActivateResponse(ok=False, reason="model_not_local", active_version=None)
    if not manifest_local or not os.path.exists(manifest_local):
        return schemas.ModelActivateResponse(ok=False, reason="manifest_not_local", active_version=None)

    # Deactivate others
    db.query(models.ModelArtifact).filter(models.ModelArtifact.is_active == True).update({"is_active": False})  # noqa: E712
    target.is_active = True
    db.commit()

    # Copy to shared dir for ML service
    _ensure_shared_dir()
    _copy_from_local(model_local, settings.MODEL_CURRENT_PT_PATH)
    _copy_from_local(manifest_local, settings.MODEL_CURRENT_MANIFEST_PATH)

    # Also write a small "current_version.json"
    with open(os.path.join(settings.MODEL_SHARED_DIR, "current_version.json"), "w", encoding="utf-8") as f:
        json.dump({"version": target.version}, f)

    return schemas.ModelActivateResponse(ok=True, active_version=target.version, reason="activated")
