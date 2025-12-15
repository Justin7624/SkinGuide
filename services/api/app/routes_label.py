# services/api/app/routes_label.py

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from . import models, schemas
from .donation import store_labels_for_sample
from .auth import require_user_auth

router = APIRouter(prefix="/v1", tags=["label"])

@router.post("/label", response_model=schemas.LabelResponse)
def label_sample(
    payload: schemas.LabelUpsert,
    session_id: str | None = None,
    db: OrmSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
):
    session_id, _dvh = require_user_auth(db, session_id, authorization, x_device_token)

    s = db.get(models.Session, session_id)
    if not s:
        return schemas.LabelResponse(ok=True, stored=False, reason="session_not_found")

    c = db.get(models.Consent, session_id)
    if not c or not bool(c.donate_for_improvement):
        return schemas.LabelResponse(ok=True, stored=False, reason="no_consent")

    for k, v in (payload.labels or {}).items():
        if v < 0.0 or v > 1.0:
            return schemas.LabelResponse(ok=True, stored=False, reason=f"bad_value:{k}")

    labels_payload = {"labels": payload.labels, "fitzpatrick": payload.fitzpatrick, "age_band": payload.age_band}

    stored, reason = store_labels_for_sample(
        db=db,
        session_id=session_id,
        roi_sha256=payload.roi_sha256,
        labels_payload=labels_payload,
    )

    return schemas.LabelResponse(ok=True, stored=stored, reason=reason, roi_sha256=payload.roi_sha256)
