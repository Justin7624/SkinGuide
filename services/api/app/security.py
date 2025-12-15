# services/api/app/security.py

import time
from .config import settings
from fastapi import Header, HTTPException

# Basic in-memory rate limiting placeholder (keep your existing one if you had Redis-backed)
_bucket = {}

def rate_limit_or_429(session_id: str) -> bool:
    now = int(time.time())
    key = (session_id, now // 60)
    _bucket[key] = _bucket.get(key, 0) + 1
    return _bucket[key] <= settings.RATE_LIMIT_PER_MIN

def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.ADMIN_API_KEY:
        raise HTTPException(503, "Admin API key not configured")
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(401, "Unauthorized")
