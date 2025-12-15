# services/api/app/routes_admin_labelqueue.py

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Dict, Optional, Tuple, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import asc, desc, func

from .db import get_db
from . import models
from .security import require_role
from .storage import get_storage
from .audit import log_audit

router = APIRouter(prefix="/v1/admin/label-queue", tags=["admin-label-queue"])

read_dep = Depends(require_role("viewer"))
label_dep = Depends(require_role("labeler"))
admin_dep = Depends(require_role("admin"))

# --------------------------
# Helpers: consensus logic
# --------------------------

def _loads(s: str) -> Dict[str, Any]:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}

def _float01(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if v != v:
            return None
        return max(0.0, min(1.0, v))
    except Exception:
        return None

def _merge_mean(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    return sum(vals) / float(len(vals))

def _consensus_from_two(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]], Dict[str, Any]]:
    """
    Returns (global_labels, region_labels, meta)
    Computes mean for keys present in both (for stability).
    """
    la = a.get("labels") if isinstance(a.get("labels"), dict) else {}
    lb = b.get("labels") if isinstance(b.get("labels"), dict) else {}

    out_global: Dict[str, float] = {}
    common_keys = set(la.keys()) & set(lb.keys())
    diffs = []

    for k in common_keys:
        va = _float01(la.get(k))
        vb = _float01(lb.get(k))
        if va is None or vb is None:
            continue
        out_global[k] = (va + vb) / 2.0
        diffs.append(abs(va - vb))

    # per-region labels
    ra = a.get("region_labels") if isinstance(a.get("region_labels"), dict) else {}
    rb = b.get("region_labels") if isinstance(b.get("region_labels"), dict) else {}

    out_regions: Dict[str, Dict[str, float]] = {}
    common_regions = set(ra.keys()) & set(rb.keys())

    for region in common_regions:
        da = ra.get(region) if isinstance(ra.get(region), dict) else {}
        dbb = rb.get(region) if isinstance(rb.get(region), dict) else {}
        r_common = set(da.keys()) & set(dbb.keys())
        r_out: Dict[str, float] = {}
        for k in r_common:
            va = _float01(da.get(k))
            vb = _float01(dbb.get(k))
            if va is None or vb is None:
                continue
            r_out[k] = (va + vb) / 2.0
            diffs.append(abs(va - vb))
        if r_out:
            out_regions[region] = r_out

    meta: Dict[str, Any] = {
        "mean_abs_diff": (sum(diffs) / float(len(diffs))) if diffs else 0.0,
        "max_abs_diff": max(diffs) if diffs else 0.0,
        "n_compared": len(diffs),
    }
    return out_global, out_regions, meta

def _pick_two_distinct_non_skip(subs: list[models.DonatedSampleLabel]) -> Optional[tuple[models.DonatedSampleLabel, models.DonatedSampleLabel]]:
    seen = set()
    picked: list[models.DonatedSampleLabel] = []
    for s in subs:
        if s.is_skip:
            continue
        if s.admin_user_id in seen:
            continue
        picked.append(s)
        seen.add(s.admin_user_id)
        if len(picked) == 2:
            return picked[0], picked[1]
    return None

def _finalize_if_consensus(db: OrmSession, donation: models.DonatedSample) -> Dict[str, Any]:
    """
    If 2 non-skip submissions exist by distinct admins and agree enough,
    write donation.labels_json (final consensus) and donation.labeled_at.

    Also handles "2 skips" -> final skip.
    Mixed skip/label or high disagreement => do not finalize.
    """
    if donation.labels_json is not None:
        return {"finalized": True, "reason": "already_final"}

    subs = (
        db.query(models.DonatedSampleLabel)
        .filter(models.DonatedSampleLabel.donated_sample_id == donation.id)
        .order_by(desc(models.DonatedSampleLabel.created_at))
        .all()
    )

    # If 2 distinct skips -> finalize skip
    skip_subs = []
    seen_skip = set()
    for s in subs:
        if not s.is_skip:
            continue
        if s.admin_user_id in seen_skip:
            continue
        skip_subs.append(s)
        seen_skip.add(s.admin_user_id)
        if len(skip_subs) == 2:
            donation.labels_json = json.dumps(
                {
                    "skipped": True,
                    "reason": "consensus_skip",
                    "finalized_at": datetime.utcnow().isoformat(),
                    "finalized_from": [
                        {"admin_user_id": s.admin_user_id, "created_at": s.created_at.isoformat()} for s in skip_subs
                    ],
                },
                ensure_ascii=False,
            )
            donation.labeled_at = datetime.utcnow()
            db.add(donation)
            return {"finalized": True, "reason": "consensus_skip"}

    pair = _pick_two_distinct_non_skip(subs)
    if not pair:
        return {"finalized": False, "reason": "need_more_labels"}

    s1, s2 = pair
    a = _loads(s1.labels_json)
    b = _loads(s2.labels_json)

    g, r, meta = _consensus_from_two(a, b)

    # Agreement guardrails (tunable):
    # - must have at least some compared keys
    # - reject if mean_abs_diff too high (conflict)
    if meta.get("n_compared", 0) == 0:
        return {"finalized": False, "reason": "no_overlap_keys"}

    if float(meta.get("mean_abs_diff", 0.0)) > 0.35 or float(meta.get("max_abs_diff", 0.0)) > 0.60:
        return {"finalized": False, "reason": "conflict_disagreement", "meta": meta}

    fitz1 = a.get("fitzpatrick")
    fitz2 = b.get("fitzpatrick")
    age1 = a.get("age_band")
    age2 = b.get("age_band")

    final = {
        "labels": g,
        "region_labels": r,
        "fitzpatrick": fitz1 if (fitz1 and fitz1 == fitz2) else None,
        "age_band": age1 if (age1 and age1 == age2) else None,
        "consensus": {
            "method": "mean_of_2_distinct_labelers",
            "meta": meta,
            "from": [
                {"admin_user_id": s1.admin_user_id, "created_at": s1.created_at.isoformat()},
                {"admin_user_id": s2.admin_user_id, "created_at": s2.created_at.isoformat()},
            ],
        },
        "finalized_at": datetime.utcnow().isoformat(),
    }

    donation.labels_json = json.dumps(final, ensure_ascii=False)
    donation.labeled_at = datetime.utcnow()
    db.add(donation)
    return {"finalized": True, "reason": "consensus_ok", "meta": meta}

# --------------------------
# Schemas
# --------------------------

class QueueItem(BaseModel):
    id: int
    roi_sha256: str
    created_at: str
    image_url: str
    metadata_json: str = ""
    is_withdrawn: bool = False

    # consensus state
    label_submissions: int = 0
    needs_more_labels: bool = True
    already_labeled_by_me: bool = False
    conflict: bool = False

class QueueResp(BaseModel):
    items: list[QueueItem] = Field(default_factory=list)

class LabelReq(BaseModel):
    # global labels (0..1)
    labels: dict = Field(default_factory=dict)

    # per-region labels:
    # {"forehead": {"redness_appearance":0.3, ...}, "left_cheek": {...}}
    region_labels: dict = Field(default_factory=dict)

    fitzpatrick: str | None = None
    age_band: str | None = None

class SkipReq(BaseModel):
    reason: str = "unclear"

class SubmissionRow(BaseModel):
    id: int
    created_at: str
    admin_user_id: int
    admin_email: str | None = None
    is_skip: bool
    labels_json: str

class SubmissionsResp(BaseModel):
    donated_sample_id: int
    final_labels_json: str | None = None
    finalized_at: str | None = None
    submissions: list[SubmissionRow] = Field(default_factory=list)

class ForceFinalizeReq(BaseModel):
    # same shape as "final" labels_json (trainer ignores extra keys)
    final: dict = Field(default_factory=dict)

# --------------------------
# Routes
# --------------------------

@router.get("/next", response_model=QueueResp, dependencies=[read_dep])
def next_items(limit: int = 20, db: OrmSession = Depends(get_db), request: Request = None):
    """
    Returns items needing consensus (labels_json is NULL).
    Filters out items already labeled by current admin user.
    """
    limit = max(1, min(int(limit), 100))

    admin_user = getattr(request.state, "admin_user", None)
    my_id = int(admin_user.id) if admin_user and getattr(admin_user, "id", 0) and int(admin_user.id) > 0 else None

    # pull extra rows so filtering doesn't starve the queue
    fetch_n = limit * 4

    rows = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.is_(None))
        .order_by(asc(models.DonatedSample.created_at))
        .limit(fetch_n)
        .all()
    )

    storage = get_storage()
    items: list[QueueItem] = []

    for d in rows:
        # count submissions
        sub_q = db.query(func.count(models.DonatedSampleLabel.id)).filter(models.DonatedSampleLabel.donated_sample_id == d.id)
        sub_count = int(sub_q.scalar() or 0)

        already_by_me = False
        if my_id is not None:
            exists = (
                db.query(models.DonatedSampleLabel.id)
                .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
                .filter(models.DonatedSampleLabel.admin_user_id == my_id)
                .first()
            )
            already_by_me = bool(exists)

        # quick conflict heuristic: any mix of skip/non-skip by distinct admins
        # or at least 2 non-skip submissions but not finalized (could be disagreement)
        non_skip_distinct = (
            db.query(func.count(func.distinct(models.DonatedSampleLabel.admin_user_id)))
            .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
            .filter(models.DonatedSampleLabel.is_skip == False)  # noqa: E712
            .scalar()
            or 0
        )
        skip_distinct = (
            db.query(func.count(func.distinct(models.DonatedSampleLabel.admin_user_id)))
            .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
            .filter(models.DonatedSampleLabel.is_skip == True)  # noqa: E712
            .scalar()
            or 0
        )
        conflict = bool(skip_distinct > 0 and non_skip_distinct > 0) or bool(non_skip_distinct >= 2 and d.labels_json is None)

        if already_by_me:
            continue

        img_url = ""
        if d.roi_image_path.startswith("s3://"):
            img_url = storage.presign_get_url(d.roi_image_path, expires_sec=900) or ""
        else:
            img_url = f"/v1/admin/label-queue/roi/{d.id}"

        needs_more = True
        if non_skip_distinct >= 1:
            needs_more = True
        if non_skip_distinct >= 2:
            # could still need more if disagreement; show as conflict
            needs_more = True

        items.append(
            QueueItem(
                id=d.id,
                roi_sha256=d.roi_sha256,
                created_at=d.created_at.isoformat(),
                image_url=img_url,
                metadata_json=d.metadata_json or "",
                is_withdrawn=bool(d.is_withdrawn),
                label_submissions=sub_count,
                needs_more_labels=needs_more,
                already_labeled_by_me=already_by_me,
                conflict=conflict,
            )
        )
        if len(items) >= limit:
            break

    return QueueResp(items=items)

@router.get("/roi/{donation_id}", dependencies=[read_dep])
def stream_roi(donation_id: int, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")

    storage = get_storage()
    lp = storage.get_local_path_if_any(d.roi_image_path)
    if not lp:
        raise HTTPException(400, "ROI not local; use presigned URL")

    return FileResponse(lp, media_type="image/jpeg")

@router.get("/{donation_id}/submissions", response_model=SubmissionsResp, dependencies=[read_dep])
def submissions(donation_id: int, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")

    subs = (
        db.query(models.DonatedSampleLabel)
        .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
        .order_by(desc(models.DonatedSampleLabel.created_at))
        .all()
    )

    # include admin emails where possible
    admin_ids = list({s.admin_user_id for s in subs})
    admins = {}
    if admin_ids:
        for u in db.query(models.AdminUser).filter(models.AdminUser.id.in_(admin_ids)).all():
            admins[u.id] = u.email

    return SubmissionsResp(
        donated_sample_id=d.id,
        final_labels_json=d.labels_json,
        finalized_at=d.labeled_at.isoformat() if d.labeled_at else None,
        submissions=[
            SubmissionRow(
                id=s.id,
                created_at=s.created_at.isoformat(),
                admin_user_id=s.admin_user_id,
                admin_email=admins.get(s.admin_user_id),
                is_skip=bool(s.is_skip),
                labels_json=s.labels_json,
            )
            for s in subs
        ],
    )

@router.post("/{donation_id}/label", dependencies=[label_dep])
def label_item(donation_id: int, payload: LabelReq, request: Request, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")
    if d.labels_json is not None:
        raise HTTPException(409, "Already finalized")

    admin_user = getattr(request.state, "admin_user", None)
    if not admin_user or int(getattr(admin_user, "id", 0)) <= 0:
        raise HTTPException(400, "Admin identity required")

    # prevent duplicate submission by same admin
    exists = (
        db.query(models.DonatedSampleLabel.id)
        .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
        .filter(models.DonatedSampleLabel.admin_user_id == int(admin_user.id))
        .first()
    )
    if exists:
        raise HTTPException(409, "You already submitted for this sample")

    submission = {
        "labels": payload.labels or {},
        "region_labels": payload.region_labels or {},
        "fitzpatrick": payload.fitzpatrick,
        "age_band": payload.age_band,
        "skipped": False,
    }

    rec = models.DonatedSampleLabel(
        donated_sample_id=d.id,
        admin_user_id=int(admin_user.id),
        created_at=datetime.utcnow(),
        is_skip=False,
        labels_json=json.dumps(submission, ensure_ascii=False),
    )
    db.add(rec)

    log_audit(
        db,
        event_type="admin_label_submitted",
        session_id=None,
        request=request,
        payload={"donated_sample_id": d.id, "roi_sha256": d.roi_sha256, "keys": list((payload.labels or {}).keys()), "regions": list((payload.region_labels or {}).keys())},
        status_code=200,
    )

    db.flush()  # ensure rec exists
    finalize_info = _finalize_if_consensus(db, d)

    log_audit(
        db,
        event_type="admin_label_finalize_attempt",
        session_id=None,
        request=request,
        payload={"donated_sample_id": d.id, "roi_sha256": d.roi_sha256, **finalize_info},
        status_code=200,
    )

    db.commit()
    return {"ok": True, "finalize": finalize_info}

@router.post("/{donation_id}/skip", dependencies=[label_dep])
def skip_item(donation_id: int, payload: SkipReq, request: Request, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")
    if d.labels_json is not None:
        raise HTTPException(409, "Already finalized")

    admin_user = getattr(request.state, "admin_user", None)
    if not admin_user or int(getattr(admin_user, "id", 0)) <= 0:
        raise HTTPException(400, "Admin identity required")

    exists = (
        db.query(models.DonatedSampleLabel.id)
        .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
        .filter(models.DonatedSampleLabel.admin_user_id == int(admin_user.id))
        .first()
    )
    if exists:
        raise HTTPException(409, "You already submitted for this sample")

    submission = {"skipped": True, "reason": payload.reason}

    rec = models.DonatedSampleLabel(
        donated_sample_id=d.id,
        admin_user_id=int(admin_user.id),
        created_at=datetime.utcnow(),
        is_skip=True,
        labels_json=json.dumps(submission, ensure_ascii=False),
    )
    db.add(rec)

    log_audit(
        db,
        event_type="admin_label_skipped",
        session_id=None,
        request=request,
        payload={"donated_sample_id": d.id, "roi_sha256": d.roi_sha256, "reason": payload.reason},
        status_code=200,
    )

    db.flush()
    finalize_info = _finalize_if_consensus(db, d)

    log_audit(
        db,
        event_type="admin_label_finalize_attempt",
        session_id=None,
        request=request,
        payload={"donated_sample_id": d.id, "roi_sha256": d.roi_sha256, **finalize_info},
        status_code=200,
    )

    db.commit()
    return {"ok": True, "finalize": finalize_info}

@router.post("/{donation_id}/force-finalize", dependencies=[admin_dep])
def force_finalize(donation_id: int, payload: ForceFinalizeReq, request: Request, db: OrmSession = Depends(get_db)):
    """
    Admin override for conflicts: sets final labels_json directly.
    """
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")

    if not isinstance(payload.final, dict) or not payload.final:
        raise HTTPException(400, "final must be a non-empty object")

    d.labels_json = json.dumps(
        {
            **payload.final,
            "finalized_at": datetime.utcnow().isoformat(),
            "finalized_by": getattr(getattr(request.state, "admin_user", None), "email", None),
            "finalized_via": "force_finalize",
        },
        ensure_ascii=False,
    )
    d.labeled_at = datetime.utcnow()
    db.add(d)

    log_audit(
        db,
        event_type="admin_force_finalize",
        session_id=None,
        request=request,
        payload={"donated_sample_id": d.id, "roi_sha256": d.roi_sha256},
        status_code=200,
    )

    db.commit()
    return {"ok": True}
