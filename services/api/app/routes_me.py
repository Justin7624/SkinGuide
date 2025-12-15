# services/api/app/routes_me.py

from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from .auth import require_user_auth
from .storage import get_storage
from . import models
from .schemas_me import DeleteMeResponse

router = APIRouter(prefix="/v1/me", tags=["me"])

@router.post("/delete", response_model=DeleteMeResponse)
def delete_me(
    session_id: str | None = None,
    db: OrmSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
):
    # Must be authenticated (in prod REQUIRE_AUTH=true)
    session_id, _dvh = require_user_auth(db, session_id, authorization, x_device_token)

    s = db.get(models.Session, session_id)
    if not s:
        # Idempotent delete
        return DeleteMeResponse(ok=True)

    storage = get_storage()

    # Delete progress images + rows
    progress_rows = db.query(models.ProgressEntry).filter(models.ProgressEntry.session_id == session_id).all()
    deleted_progress = 0
    for p in progress_rows:
        if p.roi_image_path:
            storage.delete_uri(p.roi_image_path)
        db.delete(p)
        deleted_progress += 1

    # Withdraw donations (do not use for training), delete ROI image object, clear labels
    donations = db.query(models.DonatedSample).filter(models.DonatedSample.session_id == session_id).all()
    withdrawn = 0
    now = datetime.utcnow()
    for d in donations:
        if not d.is_withdrawn:
            if d.roi_image_path:
                storage.delete_uri(d.roi_image_path)
            d.is_withdrawn = True
            d.withdrawn_at = now
            # clear labels to avoid training reuse even if a stale process ignores is_withdrawn
            d.labels_json = None
            d.labeled_at = None
            withdrawn += 1

    # Delete consent
    c = db.get(models.Consent, session_id)
    deleted_consent = False
    if c:
        db.delete(c)
        deleted_consent = True

    # Delete session itself
    db.delete(s)

    db.commit()

    return DeleteMeResponse(
        ok=True,
        deleted_progress_entries=deleted_progress,
        withdrawn_donations=withdrawn,
        deleted_consent=deleted_consent,
        deleted_session=True,
    )
