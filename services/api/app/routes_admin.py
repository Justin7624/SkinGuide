# services/api/app/routes_admin.py

from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Dict, Iterable, Optional, List, Tuple
import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import func, desc

from .db import get_db
from .security import require_admin
from . import models
from .schemas_admin import (
    AdminSummary, AdminAuditEvent, AdminAuditPage,
    AdminMetricsResponse, TimePoint, Breakdown, BreakdownItem,
    ModelTable, ModelRow
)

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# --------------------------
# helpers
# --------------------------

def _to_day(dt: datetime) -> date:
    return dt.date()

def _parse_yyyy_mm_dd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _date_range(days: int | None, start: str | None, end: str | None) -> tuple[date, date]:
    """
    Returns (start_date, end_date) inclusive.
    Defaults: last N days ending today (N=30).
    """
    today = datetime.utcnow().date()
    if end:
        end_d = _parse_yyyy_mm_dd(end)
    else:
        end_d = today

    if start:
        start_d = _parse_yyyy_mm_dd(start)
    else:
        d = int(days or 30)
        d = max(1, min(d, 365))
        start_d = end_d - timedelta(days=d - 1)

    if start_d > end_d:
        start_d, end_d = end_d, start_d

    return start_d, end_d

def _make_day_index(start_d: date, end_d: date) -> list[date]:
    out = []
    cur = start_d
    while cur <= end_d:
        out.append(cur)
        cur = cur + timedelta(days=1)
    return out

def _fill_series(day_idx: list[date], counts: Dict[date, int]) -> list[TimePoint]:
    return [TimePoint(date=d.isoformat(), value=int(counts.get(d, 0))) for d in day_idx]

def _group_count_by_day(q_rows: Iterable[tuple]) -> Dict[date, int]:
    """
    Expects rows like [(date_obj, count), ...]
    """
    out: Dict[date, int] = {}
    for d, n in q_rows:
        if d is None:
            continue
        # SQL date may come as datetime/date depending on DB
        if isinstance(d, datetime):
            dd = d.date()
        else:
            dd = d
        out[dd] = int(n or 0)
    return out

def _breakdown(rows: Iterable[tuple], limit: int = 20) -> Breakdown:
    items = []
    for k, v in rows:
        if k is None:
            k = "unknown"
        items.append(BreakdownItem(key=str(k), value=int(v or 0)))
    items = sorted(items, key=lambda x: x.value, reverse=True)[:limit]
    return Breakdown(items=items)

def _csv_stream(header: list[str], rows: Iterable[list[str]]) -> StreamingResponse:
    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        for r in rows:
            w.writerow(r)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    return StreamingResponse(gen(), media_type="text/csv")

# --------------------------
# summary + audit
# --------------------------

@router.get("/summary", response_model=AdminSummary)
def summary(db: OrmSession = Depends(get_db)):
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    total_sessions = db.query(func.count(models.Session.id)).scalar() or 0

    total_analyzes_24h = (
        db.query(func.count(models.AuditEvent.id))
        .filter(models.AuditEvent.event_type == "analyze_completed")
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
    items: list[AdminAuditEvent] = []
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

# --------------------------
# UI-ready metrics for charts
# --------------------------

@router.get("/metrics", response_model=AdminMetricsResponse)
def metrics(
    days: int | None = Query(default=30, ge=1, le=365),
    start: str | None = Query(default=None, description="YYYY-MM-DD"),
    end: str | None = Query(default=None, description="YYYY-MM-DD"),
    db: OrmSession = Depends(get_db),
):
    start_d, end_d = _date_range(days, start, end)
    day_idx = _make_day_index(start_d, end_d)

    # Sessions per day
    sess_rows = (
        db.query(func.date(models.Session.created_at), func.count(models.Session.id))
        .filter(models.Session.created_at >= datetime.combine(start_d, datetime.min.time()))
        .filter(models.Session.created_at < datetime.combine(end_d + timedelta(days=1), datetime.min.time()))
        .group_by(func.date(models.Session.created_at))
        .all()
    )
    sess_counts = _group_count_by_day(sess_rows)

    # Analyzes completed per day (audit_events)
    an_rows = (
        db.query(func.date(models.AuditEvent.created_at), func.count(models.AuditEvent.id))
        .filter(models.AuditEvent.event_type == "analyze_completed")
        .filter(models.AuditEvent.created_at >= datetime.combine(start_d, datetime.min.time()))
        .filter(models.AuditEvent.created_at < datetime.combine(end_d + timedelta(days=1), datetime.min.time()))
        .group_by(func.date(models.AuditEvent.created_at))
        .all()
    )
    an_counts = _group_count_by_day(an_rows)

    # Donations created per day
    don_rows = (
        db.query(func.date(models.DonatedSample.created_at), func.count(models.DonatedSample.id))
        .filter(models.DonatedSample.created_at >= datetime.combine(start_d, datetime.min.time()))
        .filter(models.DonatedSample.created_at < datetime.combine(end_d + timedelta(days=1), datetime.min.time()))
        .group_by(func.date(models.DonatedSample.created_at))
        .all()
    )
    don_counts = _group_count_by_day(don_rows)

    # Withdrawn per day (by withdrawn_at)
    wd_rows = (
        db.query(func.date(models.DonatedSample.withdrawn_at), func.count(models.DonatedSample.id))
        .filter(models.DonatedSample.is_withdrawn == True)  # noqa: E712
        .filter(models.DonatedSample.withdrawn_at.isnot(None))
        .filter(models.DonatedSample.withdrawn_at >= datetime.combine(start_d, datetime.min.time()))
        .filter(models.DonatedSample.withdrawn_at < datetime.combine(end_d + timedelta(days=1), datetime.min.time()))
        .group_by(func.date(models.DonatedSample.withdrawn_at))
        .all()
    )
    wd_counts = _group_count_by_day(wd_rows)

    # Labels created per day (labeled_at)
    lab_rows = (
        db.query(func.date(models.DonatedSample.labeled_at), func.count(models.DonatedSample.id))
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labeled_at.isnot(None))
        .filter(models.DonatedSample.labeled_at >= datetime.combine(start_d, datetime.min.time()))
        .filter(models.DonatedSample.labeled_at < datetime.combine(end_d + timedelta(days=1), datetime.min.time()))
        .group_by(func.date(models.DonatedSample.labeled_at))
        .all()
    )
    lab_counts = _group_count_by_day(lab_rows)

    # 24h breakdowns for dashboard widgets
    now = datetime.utcnow()
    last24 = now - timedelta(hours=24)

    ev_break = (
        db.query(models.AuditEvent.event_type, func.count(models.AuditEvent.id))
        .filter(models.AuditEvent.created_at >= last24)
        .group_by(models.AuditEvent.event_type)
        .all()
    )

    # model version breakdown based on audit payload_json (cheap substring parse)
    # Note: payload_json is sanitized; includes model_version for analyze_completed.
    mv_rows = (
        db.query(models.AuditEvent.payload_json, func.count(models.AuditEvent.id))
        .filter(models.AuditEvent.event_type == "analyze_completed")
        .filter(models.AuditEvent.created_at >= last24)
        .group_by(models.AuditEvent.payload_json)
        .all()
    )
    mv_counts: Dict[str, int] = {}
    for payload_json, n in mv_rows:
        v = "unknown"
        if payload_json:
            try:
                j = json.loads(payload_json)
                v = str(j.get("model_version") or "unknown")
            except Exception:
                v = "unknown"
        mv_counts[v] = mv_counts.get(v, 0) + int(n or 0)

    mv_break = [(k, v) for k, v in mv_counts.items()]

    return AdminMetricsResponse(
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        analyzes=_fill_series(day_idx, an_counts),
        sessions=_fill_series(day_idx, sess_counts),
        donations_created=_fill_series(day_idx, don_counts),
        donations_withdrawn=_fill_series(day_idx, wd_counts),
        labels_created=_fill_series(day_idx, lab_counts),
        event_type_breakdown_24h=_breakdown(ev_break, limit=40),
        model_version_breakdown_24h=_breakdown(mv_break, limit=20),
    )

# --------------------------
# Models table (UI-ready)
# --------------------------

@router.get("/models", response_model=ModelTable)
def models_table(db: OrmSession = Depends(get_db)):
    rows = db.query(models.ModelArtifact).order_by(desc(models.ModelArtifact.created_at)).limit(200).all()
    active = next((r for r in rows if r.is_active), None)
    return ModelTable(
        active_version=active.version if active else None,
        items=[
            ModelRow(
                version=r.version,
                created_at=r.created_at.isoformat(),
                is_active=bool(r.is_active),
                model_uri=r.model_uri,
                manifest_uri=r.manifest_uri,
                metrics_json=r.metrics_json,
            )
            for r in rows
        ],
    )

# --------------------------
# CSV Exports
# --------------------------

@router.get("/export/audit.csv")
def export_audit_csv(
    since_days: int | None = Query(default=7, ge=1, le=365),
    limit: int = Query(default=200000, ge=1, le=500000),
    db: OrmSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=int(since_days or 7))
    q = (
        db.query(models.AuditEvent)
        .filter(models.AuditEvent.created_at >= cutoff)
        .order_by(desc(models.AuditEvent.id))
        .limit(int(limit))
    )

    header = ["id", "created_at", "event_type", "session_id", "request_id", "client_ip", "payload_json"]

    def rows():
        for r in q:
            yield [
                str(r.id),
                r.created_at.isoformat(),
                r.event_type,
                r.session_id or "",
                r.request_id or "",
                r.client_ip or "",
                r.payload_json or "",
            ]

    return _csv_stream(header, rows())

@router.get("/export/sessions.csv")
def export_sessions_csv(
    since_days: int | None = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=200000, ge=1, le=500000),
    db: OrmSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=int(since_days or 30))
    q = (
        db.query(models.Session)
        .filter(models.Session.created_at >= cutoff)
        .order_by(desc(models.Session.created_at))
        .limit(int(limit))
    )
    header = ["id", "created_at", "has_device_binding"]

    def rows():
        for s in q:
            yield [
                s.id,
                s.created_at.isoformat(),
                "1" if (s.device_token_hash is not None) else "0",
            ]

    return _csv_stream(header, rows())

@router.get("/export/consents.csv")
def export_consents_csv(
    limit: int = Query(default=200000, ge=1, le=500000),
    db: OrmSession = Depends(get_db),
):
    q = db.query(models.Consent).order_by(desc(models.Consent.updated_at)).limit(int(limit))
    header = [
        "session_id",
        "store_progress_images",
        "donate_for_improvement",
        "accepted_privacy_version",
        "accepted_terms_version",
        "accepted_consent_version",
        "accepted_at",
        "updated_at",
    ]

    def rows():
        for c in q:
            yield [
                c.session_id,
                "1" if c.store_progress_images else "0",
                "1" if c.donate_for_improvement else "0",
                c.accepted_privacy_version or "",
                c.accepted_terms_version or "",
                c.accepted_consent_version or "",
                c.accepted_at.isoformat() if c.accepted_at else "",
                c.updated_at.isoformat(),
            ]

    return _csv_stream(header, rows())

@router.get("/export/donations.csv")
def export_donations_csv(
    since_days: int | None = Query(default=90, ge=1, le=3650),
    limit: int = Query(default=200000, ge=1, le=500000),
    db: OrmSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=int(since_days or 90))
    q = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.created_at >= cutoff)
        .order_by(desc(models.DonatedSample.created_at))
        .limit(int(limit))
    )

    header = [
        "id", "session_id", "created_at",
        "roi_sha256", "roi_image_path",
        "is_withdrawn", "withdrawn_at",
        "has_labels", "labeled_at",
    ]

    def rows():
        for d in q:
            yield [
                str(d.id),
                d.session_id,
                d.created_at.isoformat(),
                d.roi_sha256,
                d.roi_image_path,
                "1" if d.is_withdrawn else "0",
                d.withdrawn_at.isoformat() if d.withdrawn_at else "",
                "1" if (d.labels_json is not None) else "0",
                d.labeled_at.isoformat() if d.labeled_at else "",
            ]

    return _csv_stream(header, rows())

@router.get("/export/labels.csv")
def export_labels_csv(
    since_days: int | None = Query(default=365, ge=1, le=3650),
    limit: int = Query(default=200000, ge=1, le=500000),
    db: OrmSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=int(since_days or 365))
    q = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.isnot(None))
        .filter(models.DonatedSample.labeled_at.isnot(None))
        .filter(models.DonatedSample.labeled_at >= cutoff)
        .order_by(desc(models.DonatedSample.labeled_at))
        .limit(int(limit))
    )

    header = [
        "id", "roi_sha256", "session_id",
        "labeled_at", "fitzpatrick", "age_band",
        "labels_json",
    ]

    def rows():
        for d in q:
            fitz = ""
            age = ""
            labels_json = d.labels_json or ""
            try:
                j = json.loads(labels_json) if labels_json else {}
                fitz = str(j.get("fitzpatrick") or "")
                age = str(j.get("age_band") or "")
            except Exception:
                pass

            yield [
                str(d.id),
                d.roi_sha256,
                d.session_id,
                d.labeled_at.isoformat() if d.labeled_at else "",
                fitz,
                age,
                labels_json,
            ]

    return _csv_stream(header, rows())

@router.get("/export/models.csv")
def export_models_csv(
    limit: int = Query(default=10000, ge=1, le=100000),
    db: OrmSession = Depends(get_db),
):
    q = db.query(models.ModelArtifact).order_by(desc(models.ModelArtifact.created_at)).limit(int(limit))
    header = ["version", "created_at", "is_active", "model_uri", "manifest_uri", "metrics_json"]

    def rows():
        for m in q:
            yield [
                m.version,
                m.created_at.isoformat(),
                "1" if m.is_active else "0",
                m.model_uri,
                m.manifest_uri,
                m.metrics_json or "",
            ]

    return _csv_stream(header, rows())
