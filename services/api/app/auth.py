# services/api/app/auth.py

import base64
import hashlib
import hmac
import json
import time
from typing import Optional, Tuple

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session as OrmSession

from .config import settings
from . import models

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))

def _sign(msg: bytes) -> str:
    key = settings.SESSION_SECRET.encode("utf-8")
    return _b64url(hmac.new(key, msg, hashlib.sha256).digest())

def device_hash(device_token: str) -> str:
    # HMAC hash so raw device token never stored in DB
    key = settings.SESSION_SECRET.encode("utf-8")
    return hmac.new(key, device_token.encode("utf-8"), hashlib.sha256).hexdigest()

def mint_access_token(session_id: str, dev_hash: str, ttl_min: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sid": session_id,
        "dvh": dev_hash,
        "iat": now,
        "exp": now + int(ttl_min) * 60,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _sign(f"{h}.{p}".encode("ascii"))
    return f"{h}.{p}.{sig}"

def verify_access_token(token: str) -> dict:
    try:
        h, p, sig = token.split(".")
    except ValueError:
        raise HTTPException(401, "Invalid token")

    expected = _sign(f"{h}.{p}".encode("ascii"))
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(p))
    except Exception:
        raise HTTPException(401, "Invalid token payload")

    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        raise HTTPException(401, "Token expired")

    if "sid" not in payload or "dvh" not in payload:
        raise HTTPException(401, "Invalid token claims")

    return payload

def extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()

def require_user_auth(
    db: OrmSession,
    session_id: Optional[str],
    authorization: Optional[str],
    device_token: Optional[str],
) -> Tuple[str, str]:
    """
    Returns (session_id, dev_hash).
    If REQUIRE_AUTH=true: requires Authorization Bearer + X-Device-Token.
    If REQUIRE_AUTH=false: allows legacy session_id without headers (dev mode).
    """
    bearer = extract_bearer(authorization)

    if settings.REQUIRE_AUTH:
        if not bearer:
            raise HTTPException(401, "Missing Authorization bearer token")
        if not device_token:
            raise HTTPException(401, "Missing X-Device-Token")
        claims = verify_access_token(bearer)
        sid = claims["sid"]
        dvh = claims["dvh"]
        if device_hash(device_token) != dvh:
            raise HTTPException(401, "Device token mismatch")

        s = db.get(models.Session, sid)
        if not s:
            raise HTTPException(401, "Unknown session")
        if s.device_token_hash != dvh:
            raise HTTPException(401, "Session/device mismatch")

        return sid, dvh

    # Dev/backwards compatibility:
    if bearer and device_token:
        claims = verify_access_token(bearer)
        sid = claims["sid"]
        dvh = claims["dvh"]
        if device_hash(device_token) != dvh:
            raise HTTPException(401, "Device token mismatch")

        s = db.get(models.Session, sid)
        if not s:
            raise HTTPException(401, "Unknown session")
        if s.device_token_hash != dvh:
            raise HTTPException(401, "Session/device mismatch")
        return sid, dvh

    # Legacy mode: accept session_id query param only (dev)
    if not session_id:
        raise HTTPException(401, "Missing session_id")
    s = db.get(models.Session, session_id)
    if not s:
        raise HTTPException(401, "Unknown session")
    return session_id, s.device_token_hash or ""
