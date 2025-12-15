# services/api/app/logging_mw.py

import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

LOG = logging.getLogger("skinguide")

REDACT_HEADERS = {"authorization", "x-device-token", "cookie", "set-cookie"}

def _redact_headers(headers: dict) -> dict:
    out = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in REDACT_HEADERS:
            out[k] = "[REDACTED]"
        else:
            # keep small; avoid huge header spam
            out[k] = v if len(v) < 200 else (v[:200] + "…")
    return out

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        start = time.time()

        # Don't log request body (images / PII risk)
        safe_headers = _redact_headers(dict(request.headers))

        try:
            response: Response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            dur_ms = int((time.time() - start) * 1000)

            LOG.info(
                "request",
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query)[:400],
                    "status": status,
                    "duration_ms": dur_ms,
                    "client": request.client.host if request.client else None,
                    "headers": safe_headers,
                },
            )

        response.headers["X-Request-Id"] = rid
        return response

def configure_logging():
    # Simple JSON-ish structured logs without extra deps
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s | %(request_id)s %(method)s %(path)s %(status)s %(duration_ms)s",
    )
