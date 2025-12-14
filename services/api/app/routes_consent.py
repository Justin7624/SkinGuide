from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession
from .db import get_db
from . import models, schemas
from datetime import datetime

router = APIRouter(prefix="/v1", tags=["consent"])

@router.post("/session", response_model=schemas.SessionCreateResponse)
def create_session(db: OrmSession = Depends(get_db)):
    import uuid
    sid = str(uuid.uuid4())
    db.add(models.Session(id=sid))
    db.commit()
    # consent record created lazily
    return schemas.SessionCreateResponse(
        session_id=sid,
        store_images_default=False
    )

@router.post("/consent")
def upsert_consent(payload: schemas.ConsentUpsert, session_id: str, db: OrmSession = Depends(get_db)):
    s = db.get(models.Session, session_id)
    if not s:
        raise HTTPException(404, "Session not found")

    c = db.get(models.Consent, session_id)
    if not c:
        c = models.Consent(session_id=session_id)
        db.add(c)

    c.store_progress_images = bool(payload.store_progress_images)
    c.donate_for_improvement = bool(payload.donate_for_improvement)
    c.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
