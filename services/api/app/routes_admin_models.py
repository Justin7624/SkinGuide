# services/api/app/routes_admin_models.py

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

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


def _bias_path_for_artifact(art: models.ModelArtifact) -> Optional[str]:
    """
    publish_model.py writes bias_slices.json in the same folder as manifest.json.
    """
    try:
        base = os.path.dirname(art.manifest_uri)
        p = os.path.join(base, "bias_slices.json")
        return p if os.path.exists(p) else None
    except Exception:
        return None


def _read_bias_slices(art: models.ModelArtifact) -> Optional[Dict[str, Any]]:
    p = _bias_path_for_artifact(art)
    if not p:
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            j = json.load(f)
            return j if isinstance(j, dict) else None
    except Exception:
        return None


def _compute_worst_slice_mae(bias: Dict[str, Any], min_n: int) -> Optional[float]:
    worst = None
    for key in ("by_fitzpatrick", "by_age_band", "by_fitz_age"):
        d = bias.get(key)
        if not isinstance(d, dict):
            continue
        for _, row in d.items():
            if not isinstance(row, dict):
                continue
            n = int(row.get("n") or 0)
            mae = row.get("mae")
            if n < int(min_n):
                continue
            try:
                mae_f = float(mae)
            except Exception:
                continue
            worst = mae_f if worst is None else max(worst, mae_f)
    # fallback to overall if no slices eligible
    if worst is None:
        ov = bias.get("overall_val") if isinstance(bias.get("overall_val"), dict) else {}
        try:
            n = int(ov.get("n") or 0)
            mae = float(ov.get("mae"))
            if n >= int(min_n):
                worst = mae
        except Exception:
            pass
    return worst


def _best_overall_mae_from_metrics(art: models.ModelArtifact) -> Optional[float]:
    m = _loads(art.metrics_json or "{}")
    v = m.get("bias_overall_mae")
    try:
        return float(v)
    except Exception:
        return None


def _auto_rollback_check(
    *,
    db: OrmSession,
    stable: models.ModelArtifact,
    canary: models.ModelArtifact,
    max_increase: float,
    min_n: int,
) -> Dict[str, Any]:
    """
    Uses bias_slices.json if present; falls back to metrics_json bias_overall_mae.
    Returns dict with fields: ok(bool), reason, stable_worst, canary_worst, delta
    """
    bias_stable = _read_bias_slices(stable)
    bias_canary = _read_bias_slices(canary)

    stable_worst = _compute_worst_slice_mae(bias_stable, min_n) if bias_stable else None
    canary_worst = _compute_worst_slice_mae(bias_canary, min_n) if bias_canary else None

    # fallback if missing slices
    if stable_worst is None:
        stable_worst = _best_overall_mae_from_metrics(stable)
    if canary_worst is None:
        canary_worst = _best_overall_mae_from_metrics(canary)

    if stable_worst is None or canary_worst is None:
        return {
            "ok": True,
            "reason": "insufficient_bias_metrics_to_compare",
            "stable_worst": stable_worst,
            "canary_worst": canary_worst,
            "delta": None,
        }

    delta = float(canary_worst - stable_worst)
    if delta > float(max_increase):
        return {
            "ok": False,
            "reason": "slice_mae_degraded",
            "stable_worst": stable_worst,
            "canary_worst": canary_worst,
            "delta": delta,
        }

    return {
        "ok": True,
        "reason": "ok",
        "stable_worst": stable_worst,
        "canary_worst": canary_worst,
        "delta": delta,
    }


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


class DeploySetCanaryReq(BaseModel):
    canary_model_id: int
    canary_percent: int = 5
    enabled: bool = True

    auto_rollback_enabled: bool = True
    max_slice_mae_increase: float = 0.03
    min_slice_n: int = 50

    reason: str = "admin_set_canary"


class DeploySetPercentReq(BaseModel):
    canary_percent: int
    reason: str = "admin_set_canary_percent"


class DeployCommitReq(BaseModel):
    reason: str = "admin_commit_canary"


class DeployRollbackReq(BaseModel):
    reason: str = "admin_rollback_canary"


def _get_or_create_deploy(db: OrmSession) -> models.ModelDeployment:
    dep = db.query(models.ModelDeployment).order_by(models.ModelDeployment.id.asc()).first()
    if dep:
        return dep
    dep = models.ModelDeployment(
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        enabled=False,
        canary_model_id=None,
        canary_percent=0,
        auto_rollback_enabled=True,
        max_slice_mae_increase=0.03,
        min_slice_n=50,
        last_check_at=None,
        last_check_json=None,
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


def _get_active_model(db: OrmSession) -> Optional[models.ModelArtifact]:
    return (
        db.query(models.ModelArtifact)
        .filter(models.ModelArtifact.is_active == True)  # noqa: E712
        .order_by(desc(models.ModelArtifact.created_at))
        .first()
    )


@router.get("/list", response_model=ListResp, dependencies=[read_dep])
def list_models(db: OrmSession = Depends(get_db), limit: int = 50):
    limit = max(1, min(int(limit), 500))
    rows = (
        db.query(models.ModelArtifact)
        .order_by(desc(models.ModelArtifact.created_at))
        .limit(limit)
        .all()
    )
    active = _get_active_model(db)

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

    # When promoting a new stable, disable canary unless admin sets it again
    dep = _get_or_create_deploy(db)
    dep.updated_at = datetime.utcnow()
    dep.enabled = False
    dep.canary_percent = 0
    dep.canary_model_id = None

    log_audit(
        db,
        event_type="admin_model_promoted_stable",
        session_id=None,
        request=request,
        payload={"model_id": int(m.id), "version": m.version, "reason": payload.reason},
        status_code=200,
    )

    db.commit()
    MODEL_MANAGER.ensure_current()
    return {"ok": True, "active_version": m.version}


@router.get("/deployment", dependencies=[read_dep])
def get_deployment(db: OrmSession = Depends(get_db)):
    dep = _get_or_create_deploy(db)
    stable = _get_active_model(db)
    canary = db.get(models.ModelArtifact, int(dep.canary_model_id)) if dep.canary_model_id else None
    return {
        "ok": True,
        "deployment": {
            "enabled": bool(dep.enabled),
            "canary_percent": int(dep.canary_percent),
            "auto_rollback_enabled": bool(dep.auto_rollback_enabled),
            "max_slice_mae_increase": float(dep.max_slice_mae_increase),
            "min_slice_n": int(dep.min_slice_n),
            "canary_model_id": dep.canary_model_id,
            "last_check_at": dep.last_check_at.isoformat() if dep.last_check_at else None,
            "last_check": _loads(dep.last_check_json or "{}"),
        },
        "stable": {"id": stable.id, "version": stable.version} if stable else None,
        "canary": {"id": canary.id, "version": canary.version} if canary else None,
    }


@router.post("/deployment/set_canary", dependencies=[admin_dep])
def set_canary(payload: DeploySetCanaryReq, request: Request, db: OrmSession = Depends(get_db)):
    dep = _get_or_create_deploy(db)
    stable = _get_active_model(db)
    if not stable:
        raise HTTPException(400, "No stable active model to canary against")

    canary = db.get(models.ModelArtifact, int(payload.canary_model_id))
    if not canary:
        raise HTTPException(404, "Canary model not found")
    if canary.id == stable.id:
        raise HTTPException(400, "Canary model must differ from stable")

    pct = max(0, min(int(payload.canary_percent), 100))
    dep.updated_at = datetime.utcnow()
    dep.enabled = bool(payload.enabled) and pct > 0
    dep.canary_model_id = int(canary.id)
    dep.canary_percent = pct
    dep.auto_rollback_enabled = bool(payload.auto_rollback_enabled)
    dep.max_slice_mae_increase = float(payload.max_slice_mae_increase)
    dep.min_slice_n = int(payload.min_slice_n)

    # Auto rollback check right away (precomputed bias slices)
    check = _auto_rollback_check(
        db=db,
        stable=stable,
        canary=canary,
        max_increase=dep.max_slice_mae_increase,
        min_n=dep.min_slice_n,
    )
    dep.last_check_at = datetime.utcnow()
    dep.last_check_json = json.dumps(check, ensure_ascii=False)

    if dep.auto_rollback_enabled and not check.get("ok", True):
        # rollback immediately
        dep.enabled = False
        dep.canary_percent = 0

        log_audit(
            db,
            event_type="admin_canary_auto_rollback",
            session_id=None,
            request=request,
            payload={
                "reason": payload.reason,
                "stable_version": stable.version,
                "canary_version": canary.version,
                "check": check,
            },
            status_code=200,
        )
        db.commit()
        MODEL_MANAGER.ensure_current()
        return {"ok": True, "rolled_back": True, "check": check}

    log_audit(
        db,
        event_type="admin_canary_set",
        session_id=None,
        request=request,
        payload={
            "reason": payload.reason,
            "stable_version": stable.version,
            "canary_version": canary.version,
            "canary_percent": pct,
            "check": check,
        },
        status_code=200,
    )
    db.commit()
    MODEL_MANAGER.ensure_current()
    return {"ok": True, "rolled_back": False, "check": check}


@router.post("/deployment/set_percent", dependencies=[admin_dep])
def set_canary_percent(payload: DeploySetPercentReq, request: Request, db: OrmSession = Depends(get_db)):
    dep = _get_or_create_deploy(db)
    stable = _get_active_model(db)
    if not stable:
        raise HTTPException(400, "No stable active model")

    if not dep.canary_model_id:
        raise HTTPException(400, "No canary configured")

    canary = db.get(models.ModelArtifact, int(dep.canary_model_id))
    if not canary:
        raise HTTPException(404, "Canary model not found")

    pct = max(0, min(int(payload.canary_percent), 100))
    dep.updated_at = datetime.utcnow()
    dep.canary_percent = pct
    dep.enabled = pct > 0

    check = _auto_rollback_check(
        db=db,
        stable=stable,
        canary=canary,
        max_increase=float(dep.max_slice_mae_increase),
        min_n=int(dep.min_slice_n),
    )
    dep.last_check_at = datetime.utcnow()
    dep.last_check_json = json.dumps(check, ensure_ascii=False)

    if dep.auto_rollback_enabled and dep.enabled and not check.get("ok", True):
        dep.enabled = False
        dep.canary_percent = 0

        log_audit(
            db,
            event_type="admin_canary_auto_rollback",
            session_id=None,
            request=request,
            payload={
                "reason": payload.reason,
                "stable_version": stable.version,
                "canary_version": canary.version,
                "attempted_percent": pct,
                "check": check,
            },
            status_code=200,
        )
        db.commit()
        MODEL_MANAGER.ensure_current()
        return {"ok": True, "rolled_back": True, "check": check}

    log_audit(
        db,
        event_type="admin_canary_percent_set",
        session_id=None,
        request=request,
        payload={
            "reason": payload.reason,
            "stable_version": stable.version,
            "canary_version": canary.version,
            "canary_percent": pct,
            "check": check,
        },
        status_code=200,
    )
    db.commit()
    MODEL_MANAGER.ensure_current()
    return {"ok": True, "rolled_back": False, "check": check}


@router.post("/deployment/commit", dependencies=[admin_dep])
def commit_canary(payload: DeployCommitReq, request: Request, db: OrmSession = Depends(get_db)):
    dep = _get_or_create_deploy(db)
    stable = _get_active_model(db)
    if not stable:
        raise HTTPException(400, "No stable active model")
    if not dep.canary_model_id:
        raise HTTPException(400, "No canary configured")

    canary = db.get(models.ModelArtifact, int(dep.canary_model_id))
    if not canary:
        raise HTTPException(404, "Canary model not found")

    # optional guard: run check before commit
    check = _auto_rollback_check(
        db=db,
        stable=stable,
        canary=canary,
        max_increase=float(dep.max_slice_mae_increase),
        min_n=int(dep.min_slice_n),
    )
    dep.last_check_at = datetime.utcnow()
    dep.last_check_json = json.dumps(check, ensure_ascii=False)

    if dep.auto_rollback_enabled and not check.get("ok", True):
        dep.enabled = False
        dep.canary_percent = 0
        log_audit(
            db,
            event_type="admin_commit_blocked_auto_rollback",
            session_id=None,
            request=request,
            payload={"reason": payload.reason, "check": check, "stable": stable.version, "canary": canary.version},
            status_code=200,
        )
        db.commit()
        MODEL_MANAGER.ensure_current()
        return {"ok": True, "committed": False, "rolled_back": True, "check": check}

    # promote canary to stable
    db.query(models.ModelArtifact).filter(models.ModelArtifact.is_active == True).update({"is_active": False})  # noqa: E712
    canary.is_active = True

    # disable canary deployment after commit
    dep.updated_at = datetime.utcnow()
    dep.enabled = False
    dep.canary_percent = 0
    dep.canary_model_id = None

    log_audit(
        db,
        event_type="admin_canary_committed_to_stable",
        session_id=None,
        request=request,
        payload={"reason": payload.reason, "from_stable": stable.version, "to_stable": canary.version, "check": check},
        status_code=200,
    )
    db.commit()
    MODEL_MANAGER.ensure_current()
    return {"ok": True, "committed": True, "new_stable": canary.version, "check": check}


@router.post("/deployment/rollback", dependencies=[admin_dep])
def rollback_canary(payload: DeployRollbackReq, request: Request, db: OrmSession = Depends(get_db)):
    dep = _get_or_create_deploy(db)
    stable = _get_active_model(db)

    dep.updated_at = datetime.utcnow()
    dep.enabled = False
    dep.canary_percent = 0
    dep.canary_model_id = None

    log_audit(
        db,
        event_type="admin_canary_rolled_back",
        session_id=None,
        request=request,
        payload={"reason": payload.reason, "stable_version": stable.version if stable else None},
        status_code=200,
    )
    db.commit()
    MODEL_MANAGER.ensure_current()
    return {"ok": True}


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
