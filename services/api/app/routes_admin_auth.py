# services/api/app/routes_admin_auth.py

from __future__ import annotations

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as OrmSession

import qrcode
from io import BytesIO
from fastapi.responses import StreamingResponse

from .db import get_db
from .config import settings
from . import models
from .admin_auth import (
    hash_password, verify_password, create_admin_session,
    set_admin_cookie, clear_admin_cookie,
    totp_provisioning_uri, verify_totp,
    generate_recovery_codes, hash_recovery_codes, consume_recovery_code,
    mint_reset_token, hash_reset_token
)
from .audit import log_audit
from .security import require_role

router = APIRouter(prefix="/v1/admin/auth", tags=["admin-auth"])

# --------------------------
# Schemas
# --------------------------

class BootstrapReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)

class LoginReq(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None
    recovery_code: str | None = None

class AuthMeResp(BaseModel):
    ok: bool
    email: str | None = None
    role: str | None = None
    csrf_token: str | None = None
    expires_at: str | None = None
    totp_enabled: bool | None = None

class TotpStartResp(BaseModel):
    ok: bool
    secret: str | None = None
    otpauth_uri: str | None = None

class TotpConfirmReq(BaseModel):
    code: str

class TotpConfirmResp(BaseModel):
    ok: bool
    recovery_codes: list[str] | None = None  # show once

class TotpDisableReq(BaseModel):
    password: str
    code: str | None = None
    recovery_code: str | None = None

class ResetRequestReq(BaseModel):
    email: EmailStr

class ResetRequestResp(BaseModel):
    ok: bool
    token_debug: str | None = None  # ONLY returned if PASSWORD_RESET_DEBUG_RETURN_TOKEN=True

class ResetConfirmReq(BaseModel):
    token: str
    new_password: str = Field(min_length=10)
    totp_code: str | None = None
    recovery_code: str | None = None

class ResetConfirmResp(BaseModel):
    ok: bool

# --------------------------
# Bootstrap / login / me / logout
# --------------------------

@router.post("/bootstrap")
def bootstrap_first_admin(
    payload: BootstrapReq,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
    x_bootstrap_token: str | None = Header(default=None),
):
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
        totp_enabled=False,
    )
    db.add(u)
    db.commit()

    s = create_admin_session(db, user=u, request=request)
    u.last_login_at = datetime.utcnow()

    log_audit(db, event_type="admin_bootstrap", session_id=None, request=request, payload={})
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

    # If TOTP enabled, require either totp_code or recovery_code
    if u.totp_enabled:
        ok2 = False
        if payload.totp_code and u.totp_secret and verify_totp(u.totp_secret, payload.totp_code.strip()):
            ok2 = True
        elif payload.recovery_code and consume_recovery_code(u, payload.recovery_code.strip().upper()):
            ok2 = True
        if not ok2:
            raise HTTPException(401, "2FA required")
        # persist consumed recovery code changes (if used)
        db.add(u)

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
        totp_enabled=bool(getattr(u, "totp_enabled", False)),
    )

# --------------------------
# 2FA enrollment
# --------------------------

@router.post("/2fa/start", response_model=TotpStartResp, dependencies=[Depends(require_role("viewer"))])
def totp_start(request: Request, db: OrmSession = Depends(get_db)):
    u: models.AdminUser = request.state.admin_user
    if not u or u.id < 0:
        raise HTTPException(400, "Not supported for legacy admin key")

    # create/replace secret but do not enable until confirmed
    import pyotp
    secret = pyotp.random_base32()
    u.totp_secret = secret
    u.totp_enabled = False
    db.add(u)
    db.commit()

    uri = totp_provisioning_uri(u.email, secret)
    log_audit(db, event_type="admin_2fa_start", session_id=None, request=request, payload={})
    db.commit()

    return TotpStartResp(ok=True, secret=secret, otpauth_uri=uri)

@router.get("/2fa/qr", dependencies=[Depends(require_role("viewer"))])
def totp_qr(request: Request, db: OrmSession = Depends(get_db)):
    """
    Returns a PNG QR code for the current (unenabled or enabled) secret.
    """
    u: models.AdminUser = request.state.admin_user
    if not u or not u.totp_secret:
        raise HTTPException(400, "2FA not started")
    uri = totp_provisioning_uri(u.email, u.totp_secret)

    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@router.post("/2fa/confirm", response_model=TotpConfirmResp, dependencies=[Depends(require_role("viewer"))])
def totp_confirm(payload: TotpConfirmReq, request: Request, db: OrmSession = Depends(get_db)):
    u: models.AdminUser = request.state.admin_user
    if not u or not u.totp_secret:
        raise HTTPException(400, "2FA not started")

    code = payload.code.strip().replace(" ", "")
    if not verify_totp(u.totp_secret, code):
        raise HTTPException(400, "Invalid code")

    u.totp_enabled = True
    # generate recovery codes (show once)
    codes = generate_recovery_codes(10)
    u.recovery_codes_json = hash_recovery_codes(codes)

    db.add(u)
    log_audit(db, event_type="admin_2fa_enabled", session_id=None, request=request, payload={})
    db.commit()

    return TotpConfirmResp(ok=True, recovery_codes=codes)

@router.post("/2fa/disable", dependencies=[Depends(require_role("viewer"))])
def totp_disable(payload: TotpDisableReq, request: Request, db: OrmSession = Depends(get_db)):
    u: models.AdminUser = request.state.admin_user
    if not u:
        raise HTTPException(401, "Unauthorized")

    if not verify_password(payload.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")

    # require proof: totp OR recovery
    ok2 = False
    if payload.code and u.totp_secret and verify_totp(u.totp_secret, payload.code.strip()):
        ok2 = True
    elif payload.recovery_code and consume_recovery_code(u, payload.recovery_code.strip().upper()):
        ok2 = True

    if u.totp_enabled and not ok2:
        raise HTTPException(401, "2FA proof required")

    u.totp_enabled = False
    u.totp_secret = None
    u.recovery_codes_json = None

    db.add(u)
    log_audit(db, event_type="admin_2fa_disabled", session_id=None, request=request, payload={})
    db.commit()
    return {"ok": True}

# --------------------------
# Password reset (scaffold)
# --------------------------

@router.post("/password-reset/request", response_model=ResetRequestResp)
def password_reset_request(payload: ResetRequestReq, request: Request, db: OrmSession = Depends(get_db)):
    """
    Always returns ok=True (no user enumeration).
    In production, you'd email the token link; here we can return token in debug mode.
    """
    email = str(payload.email).lower().strip()
    u = db.query(models.AdminUser).filter(models.AdminUser.email == email).first()

    token_debug = None
    if u and u.is_active:
        token = mint_reset_token()
        rec = models.AdminPasswordReset(
            user_id=u.id,
            token_hash=hash_reset_token(token),
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=int(settings.PASSWORD_RESET_TTL_MIN)),
            used_at=None,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(rec)
        log_audit(db, event_type="admin_password_reset_requested", session_id=None, request=request, payload={})
        db.commit()

        if settings.PASSWORD_RESET_DEBUG_RETURN_TOKEN:
            token_debug = token

    # Always ok
    return ResetRequestResp(ok=True, token_debug=token_debug)

@router.post("/password-reset/confirm", response_model=ResetConfirmResp)
def password_reset_confirm(payload: ResetConfirmReq, request: Request, db: OrmSession = Depends(get_db)):
    token_hash = hash_reset_token(payload.token.strip())
    rec = db.query(models.AdminPasswordReset).filter(models.AdminPasswordReset.token_hash == token_hash).first()
    if not rec:
        raise HTTPException(400, "Invalid token")
    if rec.used_at is not None:
        raise HTTPException(400, "Token already used")
    if rec.expires_at < datetime.utcnow():
        raise HTTPException(400, "Token expired")

    u = db.get(models.AdminUser, rec.user_id)
    if not u or not u.is_active:
        raise HTTPException(400, "Invalid token")

    # If TOTP enabled, require totp or recovery
    if u.totp_enabled:
        ok2 = False
        if payload.totp_code and u.totp_secret and verify_totp(u.totp_secret, payload.totp_code.strip()):
            ok2 = True
        elif payload.recovery_code and consume_recovery_code(u, payload.recovery_code.strip().upper()):
            ok2 = True
        if not ok2:
            raise HTTPException(401, "2FA proof required")

    u.password_hash = hash_password(payload.new_password)
    rec.used_at = datetime.utcnow()

    db.add(u)
    db.add(rec)
    log_audit(db, event_type="admin_password_reset_confirmed", session_id=None, request=request, payload={})
    db.commit()

    return ResetConfirmResp(ok=True)
