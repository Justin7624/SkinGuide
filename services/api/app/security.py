# services/api/app/security.py

import time
from fastapi import Header, HTTPException
from redis import Redis
from redis.exceptions import RedisError

from .config import settings

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
    """
    Returns True if allowed; False if should be rate-limited.
    Uses a per-minute fixed window in Redis.

    Key: rl:{session}:{minute_bucket}
    TTL: 120 seconds
    """
    bucket = int(time.time() // 60)
    key = f"rl:{session_id}:{bucket}"
    window_sec = 120  # keep keys slightly longer than 60s to avoid edge thrash

    try:
        r = _redis_client()
        count = int(r.eval(_LUA_INCR_EXPIRE, 1, key, window_sec))
        return count <= int(settings.RATE_LIMIT_PER_MIN)
    except RedisError:
        # fail open by default for reliability
        return bool(settings.RATE_LIMIT_FAIL_OPEN)
    except Exception:
        return bool(settings.RATE_LIMIT_FAIL_OPEN)

def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.ADMIN_API_KEY:
        raise HTTPException(503, "Admin API key not configured")
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(401, "Unauthorized")
