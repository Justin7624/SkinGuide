import secrets
import time
import redis
from .config import settings

r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

def new_session_id() -> str:
    return secrets.token_urlsafe(24)

def rate_limit_or_429(session_id: str):
    key = f"rl:{session_id}:{int(time.time() // 60)}"
    count = r.incr(key)
    r.expire(key, 70)
    if count > settings.RATE_LIMIT_PER_MIN:
        return False
    return True
