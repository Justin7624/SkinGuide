# services/api/app/routes_consent.py

from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from . import models, schemas
from .auth import require_user_auth
from .audit import log_audit
from .routes_legal import get_current_versions  # simple reuse

router = APIRouter(prefix="/v1", tags=["consent"])

@router.post("/consent")
def upsert_consent(
    payload: schemas.ConsentUpsert,
    request: Request,
    session_id: str | None = None,
    db: OrmSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
):
    session_id, _dvh = require_user_auth(db, session_id, authorization, x_device_token)

    s = db.get(models.Session, session_id)
    if not s:
        raise HTTPException(404, "Session not found")

    current_versions = get_current_versions(db)

    # Stamp versions: use client-provided versions if present, else current (scaffolding)
    pv = payload.accepted_privacy_version or current_versions.get("privacy_policy")
    tv = payload.accepted_terms_version or current_versions.get("terms_of_use")
    cv = payload.accepted_consent_version or current_versions.get("consent_copy")

    # If legal docs aren’t configured yet, allow consent but don’t stamp
    accepted_at = datetime.utcnow() if (pv or tv or cv) else None

    rec = db.get(models.Consent, session_id)
    if not rec:
        rec = models.Consent(session_id=session_id)
        db.add(rec)

    rec.store_progress_images = bool(payload.store_progress_images)
    rec.donate_for_improvement = bool(payload.donate_for_improvement)
    rec.updated_at = datetime.utcnow()

    rec.accepted_privacy_version = pv
    rec.accepted_terms_version = tv
    rec.accepted_consent_version = cv
    rec.accepted_at = accepted_at

    log_audit(
        db,
        event_type="consent_updated",
        session_id=session_id,
        request=request,
        payload={
            "policy_versions": {"privacy": pv, "terms": tv, "consent": cv},
        },
    )

    db.commit()
    return {"ok": True}
