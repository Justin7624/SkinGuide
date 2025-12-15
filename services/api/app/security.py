# services/api/app/security.py

import time
from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from .config import settings
from .admin_auth import get_admin_session_from_request, role_at_least, require_csrf_if_cookie
from .db import SessionLocal

_redis: Redis | None = None

_LUA_INCR_EXPIRE = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("EXPIRE", KEYS[1], tonumber(ARGV[1]))
end
return current
"""

def _redis_client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis

def rate_limit_or_429(session_id: str) -> bool:
    bucket = int(time.time() // 60)
    key = f"rl:{session_id}:{bucket}"
    window_sec = 120

    try:
        r = _redis_client()
        count = int(r.eval(_LUA_INCR_EXPIRE, 1, key, window_sec))
        return count <= int(settings.RATE_LIMIT_PER_MIN)
    except RedisError:
        return bool(settings.RATE_LIMIT_FAIL_OPEN)
    except Exception:
        return bool(settings.RATE_LIMIT_FAIL_OPEN)

def require_role(required_role: str):
    """
    FastAPI dependency factory:
      - validates admin session (cookie or Bearer)
      - enforces CSRF for cookie auth on mutating requests
      - checks RBAC role level
    """
    def dep(request: Request):
        db = SessionLocal()
        try:
            adm_sess, user, is_cookie = get_admin_session_from_request(db, request)
            require_csrf_if_cookie(request, adm_sess, is_cookie)
            if not role_at_least(user.role, required_role):
                raise HTTPException(403, "Insufficient role")
            # attach for handlers if needed
            request.state.admin_user = user
            request.state.admin_session = adm_sess
            return True
        finally:
            db.close()
    return dep
