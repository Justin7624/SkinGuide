from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession
from .db import get_db
from . import models
import json, os

router = APIRouter(prefix="/v1/progress", tags=["progress"])

@router.get("/list")
def list_progress(session_id: str, db: OrmSession = Depends(get_db)):
    s = db.get(models.Session, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    rows = db.query(models.ProgressEntry).filter(models.ProgressEntry.session_id == session_id).order_by(models.ProgressEntry.created_at.desc()).limit(50).all()
    return [{"id": r.id, "created_at": r.created_at.isoformat(), "stored_image": bool(r.roi_image_path), "result": json.loads(r.result_json)} for r in rows]

@router.post("/delete_all")
def delete_all(session_id: str, db: OrmSession = Depends(get_db)):
    rows = db.query(models.ProgressEntry).filter(models.ProgressEntry.session_id == session_id).all()
    for r in rows:
        if r.roi_image_path and os.path.exists(r.roi_image_path):
            try: os.remove(r.roi_image_path)
            except: pass
        db.delete(r)
    db.commit()
    return {"ok": True}
