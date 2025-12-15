# services/api/app/audit.py

import json
from typing import Any, Optional
from fastapi import Request
from sqlalchemy.orm import Session as OrmSession
from . import models

SAFE_PAYLOAD_KEYS = {
    "roi_sha256",
    "model_version",
    "quality",
    "regions_count",
    "attributes_count",
    "stored_for_progress",
    "donation_stored",
    "donation_reason",
    "label_keys",
    "fitzpatrick",
    "age_band",
    "policy_versions",
    "deleted_progress_entries",
    "withdrawn_donations",
    "activated_model_version",
    "registered_model_version",
}

def _sanitize_payload(payload: Optional[dict]) -> Optional[str]:
    if not payload:
        return None
    safe = {}
    for k, v in payload.items():
        if k in SAFE_PAYLOAD_KEYS:
            safe[k] = v
    try:
        return json.dumps(safe, ensure_ascii=False)
    except Exception:
        return None

def log_audit(
    db: OrmSession,
    *,
    event_type: str,
    session_id: str | None = None,
    request: Request | None = None,
    payload: dict | None = None,
):
    rid = None
    cip = None
    if request is not None:
        rid = request.headers.get("X-Request-Id")
        cip = request.client.host if request.client else None

    ev = models.AuditEvent(
        event_type=event_type,
        session_id=session_id,
        request_id=rid,
        client_ip=cip,
        payload_json=_sanitize_payload(payload),
    )
    db.add(ev)
    # caller controls commit boundary
