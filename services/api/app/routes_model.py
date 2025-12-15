# services/api/app/routes_model.py

import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from .security import require_role
from . import models, schemas
from .audit import log_audit

router = APIRouter(prefix="/v1/model", tags=["model"])

@router.post("/register", dependencies=[Depends(require_role("admin"))])
def register_model(req: schemas.ModelRegisterRequest, request: Request, db: OrmSession = Depends(get_db)):
    if db.query(models.ModelArtifact).filter(models.ModelArtifact.version == req.version).first():
        raise HTTPException(409, "Version exists")

    rec = models.ModelArtifact(
        version=req.version,
        model_uri=req.model_uri,
        manifest_uri=req.manifest_uri,
        metrics_json=req.metrics_json,
        is_active=False,
        created_at=datetime.utcnow(),
    )
    db.add(rec)

    log_audit(db, event_type="model_registered", session_id=None, request=request, payload={"registered_model_version": req.version})
    db.commit()
    return {"ok": True}

@router.post("/activate", response_model=schemas.ModelActivateResponse, dependencies=[Depends(require_role("admin"))])
def activate_model(req: schemas.ModelActivateRequest, request: Request, db: OrmSession = Depends(get_db)):
    target = db.query(models.ModelArtifact).filter(models.ModelArtifact.version == req.version).first()
    if not target:
        return schemas.ModelActivateResponse(ok=False, reason="not_found", active_version=None)

    db.query(models.ModelArtifact).filter(models.ModelArtifact.is_active == True).update({"is_active": False})  # noqa: E712
    target.is_active = True

    log_audit(db, event_type="model_activated", session_id=None, request=request, payload={"activated_model_version": req.version})
    db.commit()

    return schemas.ModelActivateResponse(ok=True, active_version=req.version)
