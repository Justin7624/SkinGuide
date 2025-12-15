# services/api/app/admin_auth.py

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import HTTPException, Request, Response
from passlib.context import CryptContext
from sqlalchemy.orm import Session as OrmSession

from .config import settings
from . import models

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLE_ORDER = {"viewer": 0, "labeler": 1, "admin": 2}

def hash_password(pw: str) -> str:
    return pwd.hash(pw)

def verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return pwd.verify(pw, pw_hash)
    except Exception:
        return False

def role_at_least(user_role: str, required: str) -> bool:
    return ROLE_ORDER.get(user_role, -1) >= ROLE_ORDER.get(required, 999)

def _now() -> datetime:
    return datetime.utcnow()

def _new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"

def create_admin_session(db: OrmSession, *, user: models.AdminUser, request: Request) -> models.AdminSession:
    ttl = int(settings.ADMIN_SESSION_TTL_MIN)
    s = models.AdminSession(
        token=_new_token("adm"),
        user_id=user.id,
        created_at=_now(),
        expires_at=_now() + timedelta(minutes=ttl),
        revoked_at=None,
        csrf_token=_new_token("csrf"),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(s)
    return s

def set_admin_cookie(response: Response, token: str):
    response.set_cookie(
        key=settings.ADMIN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=bool(settings.ADMIN_COOKIE_SECURE),
        samesite=settings.ADMIN_COOKIE_SAMESITE,
        domain=settings.ADMIN_COOKIE_DOMAIN,
        path="/",
        max_age=int(settings.ADMIN_SESSION_TTL_MIN) * 60,
    )

def clear_admin_cookie(response: Response):
    response.delete_cookie(
        key=settings.ADMIN_COOKIE_NAME,
        domain=settings.ADMIN_COOKIE_DOMAIN,
        path="/",
    )

def get_admin_session_from_request(db: OrmSession, request: Request) -> Tuple[models.AdminSession, models.AdminUser, bool]:
    """
    Returns (admin_session, user, is_cookie_auth).
    - Cookie auth uses CSRF on state-changing requests.
    - Bearer auth does not require CSRF header.
    """
    auth = request.headers.get("authorization") or ""
    token = None
    is_cookie = False

    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        is_cookie = False
    else:
        token = request.cookies.get(settings.ADMIN_COOKIE_NAME)
        is_cookie = True

    # Legacy shared admin key (optional, for emergency) — prefer RBAC.
    x_admin_key = request.headers.get("x-admin-key")
    if settings.ADMIN_API_KEY and x_admin_key == settings.ADMIN_API_KEY:
        # Create a pseudo user context (admin) without DB user.
        # This keeps backwards compatibility but you can disable by leaving ADMIN_API_KEY unset.
        fake_user = models.AdminUser(id=-1, email="legacy-admin-key", password_hash="*", role="admin", is_active=True)  # type: ignore
        fake_session = models.AdminSession(id=-1, token="legacy", user_id=-1, created_at=_now(), expires_at=_now() + timedelta(days=3650), revoked_at=None, csrf_token="legacy", ip=None, user_agent=None)  # type: ignore
        return fake_session, fake_user, False

    if not token:
        raise HTTPException(401, "Admin auth required")

    s = db.query(models.AdminSession).filter(models.AdminSession.token == token).first()
    if not s or s.revoked_at is not None:
        raise HTTPException(401, "Invalid admin session")

    if s.expires_at < _now():
        raise HTTPException(401, "Admin session expired")

    u = db.get(models.AdminUser, s.user_id)
    if not u or not u.is_active:
        raise HTTPException(401, "Admin user inactive")

    return s, u, is_cookie

def require_csrf_if_cookie(request: Request, admin_session: models.AdminSession, is_cookie_auth: bool):
    if not is_cookie_auth:
        return
    # Require CSRF header on state-changing requests when using cookie auth.
    if request.method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
        csrf = request.headers.get("x-csrf-token")
        if not csrf or csrf != admin_session.csrf_token:
            raise HTTPException(403, "CSRF token missing/invalid")
