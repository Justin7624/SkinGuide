# services/api/app/routes_legal.py

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import desc

from .db import get_db
from .security import require_admin
from . import models
from .schemas_legal import LegalDoc, LegalBundle, UpsertLegalDocRequest, UpsertLegalDocResponse, DocKey

router = APIRouter(prefix="/v1/legal", tags=["legal"])

def _latest_doc(db: OrmSession, key: str) -> models.PolicyDocument | None:
    return (
        db.query(models.PolicyDocument)
        .filter(models.PolicyDocument.key == key)
        .filter(models.PolicyDocument.is_active == True)  # noqa: E712
        .order_by(desc(models.PolicyDocument.effective_at), desc(models.PolicyDocument.id))
        .first()
    )

def get_current_versions(db: OrmSession) -> dict:
    out = {}
    for k in ("privacy_policy", "terms_of_use", "consent_copy"):
        d = _latest_doc(db, k)
        out[k] = d.version if d else None
    return out

@router.get("/bundle", response_model=LegalBundle)
def legal_bundle(db: OrmSession = Depends(get_db)):
    p = _latest_doc(db, "privacy_policy")
    t = _latest_doc(db, "terms_of_use")
    c = _latest_doc(db, "consent_copy")
    if not p or not t or not c:
        raise HTTPException(503, "Legal documents not configured")

    return LegalBundle(
        privacy_policy=LegalDoc(key="privacy_policy", version=p.version, effective_at=p.effective_at.isoformat(), body_markdown=p.body_markdown),
        terms_of_use=LegalDoc(key="terms_of_use", version=t.version, effective_at=t.effective_at.isoformat(), body_markdown=t.body_markdown),
        consent_copy=LegalDoc(key="consent_copy", version=c.version, effective_at=c.effective_at.isoformat(), body_markdown=c.body_markdown),
    )

@router.get("/{key}", response_model=LegalDoc)
def legal_doc(key: DocKey, db: OrmSession = Depends(get_db)):
    d = _latest_doc(db, key)
    if not d:
        raise HTTPException(404, "Not found")
    return LegalDoc(key=key, version=d.version, effective_at=d.effective_at.isoformat(), body_markdown=d.body_markdown)

@router.post("/upsert", dependencies=[Depends(require_admin)], response_model=UpsertLegalDocResponse)
def upsert_legal(req: UpsertLegalDocRequest, db: OrmSession = Depends(get_db)):
    exists = (
        db.query(models.PolicyDocument)
        .filter(models.PolicyDocument.key == req.key)
        .filter(models.PolicyDocument.version == req.version)
        .first()
    )
    if exists:
        return UpsertLegalDocResponse(ok=False, reason="version_exists")

    eff = datetime.utcnow()
    if req.effective_at:
        try:
            eff = datetime.fromisoformat(req.effective_at.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return UpsertLegalDocResponse(ok=False, reason="bad_effective_at")

    doc = models.PolicyDocument(
        key=req.key,
        version=req.version,
        effective_at=eff,
        body_markdown=req.body_markdown,
        is_active=True,
    )
    db.add(doc)
    db.commit()
    return UpsertLegalDocResponse(ok=True)
