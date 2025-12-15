# services/api/app/routes_admin_models.py

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import desc

from .db import get_db
from . import models
from .security import require_role
from .audit import log_audit
from .storage import get_storage
from .ml.model_manager import MODEL_MANAGER

router = APIRouter(prefix="/v1/admin/models", tags=["admin-models"])

read_dep = Depends(require_role("viewer"))
admin_dep = Depends(require_role("admin"))


def _loads(s: str) -> Dict[str, Any]:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


class ModelRow(BaseModel):
    id: int
    version: str
    created_at: str
    is_active: bool
    model_uri: str
    manifest_uri: str
    model_card_uri: str | None = None
    metrics: dict = Field(default_factory=dict)


class ListResp(BaseModel):
    active_version: str | None = None
    items: list[ModelRow] = Field(default_factory=list)


class PromoteReq(BaseModel):
    reason: str = "admin_promote"


@router.get("/list", response_model=ListResp, dependencies=[read_dep])
def list_models(db: OrmSession = Depends(get_db), limit: int = 50):
    limit = max(1, min(int(limit), 500))
    rows = (
        db.query(models.ModelArtifact)
        .order_by(desc(models.ModelArtifact.created_at))
        .limit(limit)
        .all()
    )
    active = (
        db.query(models.ModelArtifact)
        .filter(models.ModelArtifact.is_active == True)  # noqa: E712
        .order_by(desc(models.ModelArtifact.created_at))
        .first()
    )

    items = []
    for r in rows:
        items.append(
            ModelRow(
                id=int(r.id),
                version=r.version,
                created_at=r.created_at.isoformat(),
                is_active=bool(r.is_active),
                model_uri=r.model_uri,
                manifest_uri=r.manifest_uri,
                model_card_uri=r.model_card_uri,
                metrics=_loads(r.metrics_json or "{}"),
            )
        )

    return ListResp(active_version=(active.version if active else None), items=items)


@router.get("/active", dependencies=[read_dep])
def active_info():
    return {"ok": True, "model": MODEL_MANAGER.active_info()}


@router.post("/{model_id}/promote", dependencies=[admin_dep])
def promote_model(model_id: int, payload: PromoteReq, request: Request, db: OrmSession = Depends(get_db)):
    m = db.get(models.ModelArtifact, int(model_id))
    if not m:
        raise HTTPException(404, "Model not found")

    # deactivate all
    db.query(models.ModelArtifact).filter(models.ModelArtifact.is_active == True).update(  # noqa: E712
        {"is_active": False}
    )
    m.is_active = True
    db.add(m)

    log_audit(
        db,
        event_type="admin_model_promoted",
        session_id=None,
        request=request,
        payload={"model_id": int(m.id), "version": m.version, "reason": payload.reason},
        status_code=200,
    )

    db.commit()

    # trigger manager to pick it up quickly
    MODEL_MANAGER.ensure_current()
    return {"ok": True, "active_version": m.version}


@router.get("/{model_id}/card", response_class=PlainTextResponse, dependencies=[read_dep])
def get_model_card(model_id: int, db: OrmSession = Depends(get_db)):
    m = db.get(models.ModelArtifact, int(model_id))
    if not m:
        raise HTTPException(404, "Model not found")
    if not m.model_card_uri:
        raise HTTPException(404, "No model card for this artifact")

    storage = get_storage()
    uri = m.model_card_uri
    if uri.startswith("s3://"):
        lp = storage.get_local_path_if_any(uri)
        if not lp:
            raise HTTPException(400, "Model card not cached locally for s3 uri")
        return PlainTextResponse(open(lp, "r", encoding="utf-8").read())

    if not os.path.exists(uri):
        raise HTTPException(404, "Model card file missing")
    return PlainTextResponse(open(uri, "r", encoding="utf-8").read())


@router.get("/{model_id}/manifest", dependencies=[read_dep])
def get_manifest(model_id: int, db: OrmSession = Depends(get_db)):
    m = db.get(models.ModelArtifact, int(model_id))
    if not m:
        raise HTTPException(404, "Model not found")

    storage = get_storage()
    uri = m.manifest_uri
    if uri.startswith("s3://"):
        lp = storage.get_local_path_if_any(uri)
        if not lp:
            raise HTTPException(400, "Manifest not cached locally for s3 uri")
        return FileResponse(lp, media_type="application/json")

    if not os.path.exists(uri):
        raise HTTPException(404, "Manifest missing")
    return FileResponse(uri, media_type="application/json")


@router.get("/{model_id}/metrics.json", dependencies=[read_dep])
def get_metrics_json(model_id: int, db: OrmSession = Depends(get_db)):
    m = db.get(models.ModelArtifact, int(model_id))
    if not m:
        raise HTTPException(404, "Model not found")
    return _loads(m.metrics_json or "{}")
