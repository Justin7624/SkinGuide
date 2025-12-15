# services/api/app/routes_admin_auth.py

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from .config import settings
from . import models
from .admin_auth import hash_password, verify_password, create_admin_session, set_admin_cookie, clear_admin_cookie
from .audit import log_audit
from .security import require_role

router = APIRouter(prefix="/v1/admin/auth", tags=["admin-auth"])

class BootstrapReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)

class LoginReq(BaseModel):
    email: EmailStr
    password: str

class AuthMeResp(BaseModel):
    ok: bool
    email: str | None = None
    role: str | None = None
    csrf_token: str | None = None
    expires_at: str | None = None

@router.post("/bootstrap")
def bootstrap_first_admin(
    payload: BootstrapReq,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
    x_bootstrap_token: str | None = Header(default=None),
):
    """
    Create the FIRST admin user (role=admin) if none exists.
    Protected by ADMIN_BOOTSTRAP_TOKEN env.
    """
    if not settings.ADMIN_BOOTSTRAP_TOKEN:
        raise HTTPException(503, "ADMIN_BOOTSTRAP_TOKEN not configured")
    if not x_bootstrap_token or x_bootstrap_token != settings.ADMIN_BOOTSTRAP_TOKEN:
        raise HTTPException(401, "Invalid bootstrap token")

    existing = db.query(models.AdminUser).count()
    if existing and existing > 0:
        raise HTTPException(409, "Admin already initialized")

    u = models.AdminUser(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role="admin",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(u)
    db.commit()

    # login immediately
    s = create_admin_session(db, user=u, request=request)
    u.last_login_at = datetime.utcnow()

    log_audit(db, event_type="admin_bootstrap", session_id=None, request=request, payload={"registered_model_version": None})
    db.commit()

    set_admin_cookie(response, s.token)
    return {"ok": True}

@router.post("/login")
def login(
    payload: LoginReq,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
):
    u = db.query(models.AdminUser).filter(models.AdminUser.email == str(payload.email).lower()).first()
    if not u or not u.is_active:
        raise HTTPException(401, "Invalid credentials")
    if not verify_password(payload.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")

    s = create_admin_session(db, user=u, request=request)
    u.last_login_at = datetime.utcnow()

    log_audit(db, event_type="admin_login", session_id=None, request=request, payload={})
    db.commit()

    set_admin_cookie(response, s.token)
    return {"ok": True}

@router.post("/logout", dependencies=[Depends(require_role("viewer"))])
def logout(
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
):
    # revoke the session if it exists
    token = request.cookies.get(settings.ADMIN_COOKIE_NAME)
    if token:
        s = db.query(models.AdminSession).filter(models.AdminSession.token == token).first()
        if s and s.revoked_at is None:
            s.revoked_at = datetime.utcnow()
            log_audit(db, event_type="admin_logout", session_id=None, request=request, payload={})
            db.commit()

    clear_admin_cookie(response)
    return {"ok": True}

@router.get("/me", response_model=AuthMeResp, dependencies=[Depends(require_role("viewer"))])
def me(request: Request, db: OrmSession = Depends(get_db)):
    u = getattr(request.state, "admin_user", None)
    s = getattr(request.state, "admin_session", None)
    if not u or not s:
        return AuthMeResp(ok=False)
    return AuthMeResp(
        ok=True,
        email=u.email,
        role=u.role,
        csrf_token=s.csrf_token,
        expires_at=s.expires_at.isoformat(),
    )
