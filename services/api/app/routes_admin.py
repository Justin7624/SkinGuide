# services/api/app/routes_admin.py

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import func, desc

from .db import get_db
from .security import require_admin
from . import models
from .schemas_admin import AdminSummary, AdminAuditEvent, AdminAuditPage

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])

@router.get("/summary", response_model=AdminSummary)
def summary(db: OrmSession = Depends(get_db)):
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    total_sessions = db.query(func.count(models.Session.id)).scalar() or 0

    total_analyzes_24h = (
        db.query(func.count(models.AuditEvent.id))
        .filter(models.AuditEvent.event_type == "analyze_called")
        .filter(models.AuditEvent.created_at >= day_ago)
        .scalar()
        or 0
    )

    total_donations = db.query(func.count(models.DonatedSample.id)).scalar() or 0
    total_donations_withdrawn = (
        db.query(func.count(models.DonatedSample.id))
        .filter(models.DonatedSample.is_withdrawn == True)  # noqa: E712
        .scalar()
        or 0
    )

    total_labeled = (
        db.query(func.count(models.DonatedSample.id))
        .filter(models.DonatedSample.labels_json.isnot(None))
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .scalar()
        or 0
    )

    consents_total = db.query(func.count(models.Consent.session_id)).scalar() or 0
    opt_progress = (
        db.query(func.count(models.Consent.session_id))
        .filter(models.Consent.store_progress_images == True)  # noqa: E712
        .scalar()
        or 0
    )
    opt_donate = (
        db.query(func.count(models.Consent.session_id))
        .filter(models.Consent.donate_for_improvement == True)  # noqa: E712
        .scalar()
        or 0
    )

    consent_opt_in_progress_pct = (opt_progress / consents_total * 100.0) if consents_total else 0.0
    consent_opt_in_donate_pct = (opt_donate / consents_total * 100.0) if consents_total else 0.0

    active = db.query(models.ModelArtifact).filter(models.ModelArtifact.is_active == True).first()  # noqa: E712
    active_version = active.version if active else None

    return AdminSummary(
        total_sessions=int(total_sessions),
        total_analyzes_24h=int(total_analyzes_24h),
        total_donations=int(total_donations),
        total_donations_withdrawn=int(total_donations_withdrawn),
        total_labeled=int(total_labeled),
        consent_opt_in_progress_pct=float(round(consent_opt_in_progress_pct, 2)),
        consent_opt_in_donate_pct=float(round(consent_opt_in_donate_pct, 2)),
        active_model_version=active_version,
    )

@router.get("/audit", response_model=AdminAuditPage)
def audit(
    before_id: int | None = None,
    limit: int = 100,
    db: OrmSession = Depends(get_db),
):
    limit = max(1, min(int(limit), 500))

    q = db.query(models.AuditEvent).order_by(desc(models.AuditEvent.id))
    if before_id is not None:
        q = q.filter(models.AuditEvent.id < int(before_id))

    rows = q.limit(limit).all()
    items = []
    for r in rows:
        items.append(AdminAuditEvent(
            id=r.id,
            created_at=r.created_at.isoformat(),
            event_type=r.event_type,
            session_id=r.session_id,
            request_id=r.request_id,
            client_ip=r.client_ip,
            payload_json=r.payload_json,
        ))

    next_before = items[-1].id if items else None
    return AdminAuditPage(items=items, next_before_id=next_before)
