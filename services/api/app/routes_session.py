# services/api/app/routes_session.py

import uuid
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from .config import settings
from . import models
from .auth import device_hash, mint_access_token

router = APIRouter(prefix="/v1", tags=["session"])

@router.post("/session")
def create_session(
    db: OrmSession = Depends(get_db),
    x_device_token: str | None = Header(default=None),
):
    """
    If X-Device-Token is provided, bind the session to that device and return a bearer token.
    In production, REQUIRE_AUTH should be true and clients must send X-Device-Token.
    """
    if settings.REQUIRE_AUTH and not x_device_token:
        raise HTTPException(401, "Missing X-Device-Token")

    sid = uuid.uuid4().hex
    dvh = device_hash(x_device_token) if x_device_token else None

    s = models.Session(id=sid, device_token_hash=dvh)
    db.add(s)
    db.commit()

    token = None
    if dvh:
        token = mint_access_token(sid, dvh, settings.ACCESS_TOKEN_TTL_MIN)

    return {"session_id": sid, "access_token": token}
