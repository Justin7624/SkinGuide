# services/api/app/audit.py

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session as OrmSession

from . import models

def _safe_json(payload: Any) -> str | None:
    if payload is None:
        return None
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        try:
            return json.dumps({"_unserializable": True, "repr": repr(payload)}, ensure_ascii=False)
        except Exception:
            return None

def log_audit(
    db: OrmSession,
    *,
    event_type: str,
    session_id: str | None,
    request: Request | None,
    payload: Dict[str, Any] | None = None,
    status_code: int | None = None,
):
    """
    Hardened audit logger:
      - captures actor (admin vs user), admin identity if present
      - captures path/method/ua/ip/request_id
      - payload_json stores structured details (avoid sensitive data!)
    """
    admin_user = None
    if request is not None:
        admin_user = getattr(request.state, "admin_user", None)

    request_id = None
    client_ip = None
    ua = None
    path = None
    method = None

    if request is not None:
        request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
        client_ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        path = request.url.path
        method = request.method

    actor_type = None
    admin_user_id = None
    admin_email = None

    if admin_user is not None:
        actor_type = "admin"
        try:
            # legacy key uses fake user id=-1
            if getattr(admin_user, "id", None) is not None and int(admin_user.id) > 0:
                admin_user_id = int(admin_user.id)
            admin_email = getattr(admin_user, "email", None)
        except Exception:
            pass
    elif session_id is not None:
        actor_type = "user"

    ae = models.AuditEvent(
        created_at=datetime.utcnow(),
        event_type=event_type,
        session_id=session_id,
        request_id=request_id,
        client_ip=client_ip,
        user_agent=ua,
        path=path,
        method=method,
        status_code=status_code,
        actor_type=actor_type,
        admin_user_id=admin_user_id,
        admin_email=admin_email,
        payload_json=_safe_json(payload),
    )
    db.add(ae)
