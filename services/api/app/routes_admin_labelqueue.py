# services/api/app/routes_admin_labelqueue.py

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any, Dict, Optional, Tuple, List

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import asc, desc, func

from .db import get_db
from . import models
from .security import require_role
from .storage import get_storage
from .audit import log_audit
from .config import settings

router = APIRouter(prefix="/v1/admin/label-queue", tags=["admin-label-queue"])

read_dep = Depends(require_role("viewer"))
label_dep = Depends(require_role("labeler"))
admin_dep = Depends(require_role("admin"))

# --------------------------
# Helpers
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

def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    vs = sorted(vals)
    m = len(vs) // 2
    if len(vs) % 2 == 1:
        return vs[m]
    return (vs[m - 1] + vs[m]) / 2.0

def _mean(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    return sum(vals) / float(len(vals))

def _distinct_latest_submissions(
    subs: list[models.DonatedSampleLabel],
    *,
    n: int,
    non_skip: bool
) -> list[models.DonatedSampleLabel]:
    """
    Picks up to n latest submissions by distinct admins.
    """
    out: list[models.DonatedSampleLabel] = []
    seen = set()
    for s in subs:
        if non_skip and s.is_skip:
            continue
        if (not non_skip) and (not s.is_skip):
            continue
        if s.admin_user_id in seen:
            continue
        out.append(s)
        seen.add(s.admin_user_id)
        if len(out) >= n:
            break
    return out

def _pairwise_abs_diffs(values: List[float]) -> List[float]:
    diffs = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            diffs.append(abs(values[i] - values[j]))
    return diffs

def _consensus_from_n(submissions: list[models.DonatedSampleLabel]) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]], Dict[str, Any]]:
    """
    Uses intersection of keys/regions across all provided submissions.
    For N=2: mean; For N>=3: median.
    """
    parsed = [_loads(s.labels_json) for s in submissions]
    N = len(parsed)

    def agg(vals: List[float]) -> Optional[float]:
        return _mean(vals) if N == 2 else _median(vals)

    # Global labels
    label_dicts = []
    for p in parsed:
        ld = p.get("labels") if isinstance(p.get("labels"), dict) else {}
        label_dicts.append(ld)

    common_keys = set(label_dicts[0].keys()) if label_dicts else set()
    for ld in label_dicts[1:]:
        common_keys &= set(ld.keys())

    out_global: Dict[str, float] = {}
    diffs_all: List[float] = []

    for k in common_keys:
        vals = []
        for ld in label_dicts:
            v = _float01(ld.get(k))
            if v is None:
                vals = []
                break
            vals.append(v)
        if not vals:
            continue
        out_global[k] = float(agg(vals) or 0.0)
        diffs_all.extend(_pairwise_abs_diffs(vals))

    # Per-region labels
    region_dicts = []
    for p in parsed:
        rd = p.get("region_labels") if isinstance(p.get("region_labels"), dict) else {}
        region_dicts.append(rd)

    common_regions = set(region_dicts[0].keys()) if region_dicts else set()
    for rd in region_dicts[1:]:
        common_regions &= set(rd.keys())

    out_regions: Dict[str, Dict[str, float]] = {}
    for region in common_regions:
        r_label_dicts = []
        for rd in region_dicts:
            d = rd.get(region) if isinstance(rd.get(region), dict) else {}
            r_label_dicts.append(d)

        r_common_keys = set(r_label_dicts[0].keys()) if r_label_dicts else set()
        for d in r_label_dicts[1:]:
            r_common_keys &= set(d.keys())

        r_out: Dict[str, float] = {}
        for k in r_common_keys:
            vals = []
            for d in r_label_dicts:
                v = _float01(d.get(k))
                if v is None:
                    vals = []
                    break
                vals.append(v)
            if not vals:
                continue
            r_out[k] = float(agg(vals) or 0.0)
            diffs_all.extend(_pairwise_abs_diffs(vals))
        if r_out:
            out_regions[region] = r_out

    meta: Dict[str, Any] = {
        "n_labelers": N,
        "n_compared": len(diffs_all),
        "mean_abs_diff": (sum(diffs_all) / float(len(diffs_all))) if diffs_all else 0.0,
        "max_abs_diff": max(diffs_all) if diffs_all else 0.0,
        "aggregation": "mean" if N == 2 else "median",
    }
    return out_global, out_regions, meta

def _consensus_ready(db: OrmSession, donation_id: int) -> Tuple[bool, Dict[str, Any]]:
    """
    Returns (ready, detail)
    """
    subs = (
        db.query(models.DonatedSampleLabel)
        .filter(models.DonatedSampleLabel.donated_sample_id == donation_id)
        .order_by(desc(models.DonatedSampleLabel.created_at))
        .all()
    )
    need_n = max(2, int(settings.LABEL_CONSENSUS_N))

    non_skip = _distinct_latest_submissions(subs, n=need_n, non_skip=True)
    skip = _distinct_latest_submissions(subs, n=need_n, non_skip=False)

    skip_distinct = len(skip)
    non_skip_distinct = len(non_skip)

    # Pure skip consensus
    if skip_distinct >= need_n and non_skip_distinct == 0:
        return True, {"mode": "skip", "need_n": need_n, "skip_distinct": skip_distinct}

    # Mixed skip/non-skip => conflict; do not auto finalize
    if skip_distinct > 0 and non_skip_distinct > 0:
        return False, {"mode": "mixed", "conflict": True, "need_n": need_n, "skip_distinct": skip_distinct, "non_skip_distinct": non_skip_distinct}

    if non_skip_distinct < need_n:
        return False, {"mode": "label", "need_n": need_n, "non_skip_distinct": non_skip_distinct}

    # Have enough non-skip labelers
    g, r, meta = _consensus_from_n(non_skip[:need_n])

    # Need overlap keys, otherwise not meaningful
    if meta.get("n_compared", 0) == 0:
        return False, {"mode": "label", "need_n": need_n, "reason": "no_overlap_keys", "conflict": True, "meta": meta}

    # Disagreement gate
    if float(meta.get("mean_abs_diff", 0.0)) > float(settings.LABEL_MEAN_ABS_DIFF_MAX) or float(meta.get("max_abs_diff", 0.0)) > float(settings.LABEL_MAX_ABS_DIFF_MAX):
        return False, {"mode": "label", "need_n": need_n, "reason": "disagreement", "conflict": True, "meta": meta}

    return True, {"mode": "label", "need_n": need_n, "meta": meta, "preview": {"labels": g, "region_labels": r}}

def _finalize_if_consensus(db: OrmSession, donation: models.DonatedSample) -> Dict[str, Any]:
    if donation.labels_json is not None:
        return {"finalized": True, "reason": "already_final"}

    ready, detail = _consensus_ready(db, donation.id)
    need_n = int(detail.get("need_n", max(2, int(settings.LABEL_CONSENSUS_N))))

    if not ready:
        return {"finalized": False, "reason": detail.get("reason") or "not_ready", **detail}

    subs = (
        db.query(models.DonatedSampleLabel)
        .filter(models.DonatedSampleLabel.donated_sample_id == donation.id)
        .order_by(desc(models.DonatedSampleLabel.created_at))
        .all()
    )

    if detail.get("mode") == "skip":
        picked = _distinct_latest_submissions(subs, n=need_n, non_skip=False)
        donation.labels_json = json.dumps(
            {
                "skipped": True,
                "reason": "consensus_skip",
                "consensus": {
                    "method": f"{need_n}_distinct_labelers",
                    "from": [{"admin_user_id": s.admin_user_id, "created_at": s.created_at.isoformat()} for s in picked],
                },
                "finalized_at": datetime.utcnow().isoformat(),
            },
            ensure_ascii=False,
        )
        donation.labeled_at = datetime.utcnow()
        db.add(donation)
        return {"finalized": True, "reason": "consensus_skip"}

    # label mode
    picked = _distinct_latest_submissions(subs, n=need_n, non_skip=True)
    g, r, meta = _consensus_from_n(picked[:need_n])

    # Only keep fitz/age if all agree (strict)
    parsed = [_loads(s.labels_json) for s in picked[:need_n]]
    fitz = parsed[0].get("fitzpatrick") if parsed else None
    age = parsed[0].get("age_band") if parsed else None
    for p in parsed[1:]:
        if p.get("fitzpatrick") != fitz:
            fitz = None
        if p.get("age_band") != age:
            age = None

    final = {
        "labels": g,
        "region_labels": r,
        "fitzpatrick": fitz,
        "age_band": age,
        "consensus": {
            "method": meta.get("aggregation") + f"_of_{need_n}_distinct_labelers",
            "meta": meta,
            "from": [{"admin_user_id": s.admin_user_id, "created_at": s.created_at.isoformat()} for s in picked[:need_n]],
        },
        "finalized_at": datetime.utcnow().isoformat(),
    }
    donation.labels_json = json.dumps(final, ensure_ascii=False)
    donation.labeled_at = datetime.utcnow()
    db.add(donation)
    return {"finalized": True, "reason": "consensus_ok", "meta": meta}

def _conflict_reason(db: OrmSession, donation_id: int) -> Dict[str, Any]:
    ready, detail = _consensus_ready(db, donation_id)
    if ready:
        return {"conflict": False}
    # If detail says conflict or mixed/disagreement => conflict
    if detail.get("conflict") or detail.get("mode") == "mixed" or detail.get("reason") in ("disagreement", "no_overlap_keys"):
        return {"conflict": True, **detail}
    return {"conflict": False, **detail}

# --------------------------
# IRR helpers
# --------------------------

def _bin5(x01: float) -> int:
    # 0..1 -> 0..4
    x = max(0.0, min(1.0, float(x01)))
    return min(4, int(x * 5.0))  # [0,1) -> 0..4 ; 1.0 -> 5 -> clipped

def _weighted_kappa_quadratic(a: List[int], b: List[int], k: int = 5) -> Optional[float]:
    """
    Cohen's weighted kappa with quadratic weights on k categories.
    """
    if len(a) != len(b) or len(a) < 5:
        return None
    n = len(a)

    # confusion matrix
    O = [[0 for _ in range(k)] for __ in range(k)]
    for i in range(n):
        O[a[i]][b[i]] += 1

    # marginals
    ra = [sum(O[i][j] for j in range(k)) for i in range(k)]
    cb = [sum(O[i][j] for i in range(k)) for j in range(k)]

    # expected
    E = [[(ra[i] * cb[j]) / float(n) for j in range(k)] for i in range(k)]

    # weights: 1 - ((i-j)^2/(k-1)^2)
    denom = float((k - 1) ** 2) if k > 1 else 1.0
    W = [[1.0 - ((i - j) ** 2) / denom for j in range(k)] for i in range(k)]

    num = 0.0
    den = 0.0
    for i in range(k):
        for j in range(k):
            num += W[i][j] * O[i][j]
            den += W[i][j] * E[i][j]

    if den == 0:
        return None
    return 1.0 - (num / den)

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

    label_submissions: int = 0
    already_labeled_by_me: bool = False
    conflict: bool = False
    conflict_detail: dict = Field(default_factory=dict)

class QueueResp(BaseModel):
    items: list[QueueItem] = Field(default_factory=list)

class LabelReq(BaseModel):
    labels: dict = Field(default_factory=dict)
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
    final: dict = Field(default_factory=dict)

class ConflictReviewResp(BaseModel):
    donated_sample_id: int
    roi_sha256: str
    created_at: str
    metadata_json: str
    conflict_detail: dict = Field(default_factory=dict)
    submissions: list[SubmissionRow] = Field(default_factory=list)
    suggested_final: dict | None = None

class IRRLabelStat(BaseModel):
    key: str
    n_pairs: int
    mae: float | None = None
    pearson_r: float | None = None
    weighted_kappa_5bin: float | None = None

class IRRResp(BaseModel):
    days: int
    samples_used: int
    consensus_n: int
    global_stats: list[IRRLabelStat] = Field(default_factory=list)
    region_stats: list[IRRLabelStat] = Field(default_factory=list)

# --------------------------
# Core list endpoints
# --------------------------

@router.get("/next", response_model=QueueResp, dependencies=[read_dep])
def next_items(limit: int = 20, db: OrmSession = Depends(get_db), request: Request = None):
    """
    Returns items needing labels (not finalized) and not withdrawn.
    Excludes items already labeled by current admin.
    """
    limit = max(1, min(int(limit), 100))
    admin_user = getattr(request.state, "admin_user", None)
    my_id = int(admin_user.id) if admin_user and int(getattr(admin_user, "id", 0)) > 0 else None

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
        # skip conflicts here; those go to /conflicts
        cinfo = _conflict_reason(db, d.id)
        if cinfo.get("conflict"):
            continue

        # exclude already labeled by me
        already_by_me = False
        if my_id is not None:
            exists = (
                db.query(models.DonatedSampleLabel.id)
                .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
                .filter(models.DonatedSampleLabel.admin_user_id == my_id)
                .first()
            )
            already_by_me = bool(exists)
        if already_by_me:
            continue

        sub_count = int(
            (db.query(func.count(models.DonatedSampleLabel.id))
             .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
             .scalar() or 0)
        )

        if d.roi_image_path.startswith("s3://"):
            img_url = storage.presign_get_url(d.roi_image_path, expires_sec=900) or ""
        else:
            img_url = f"/v1/admin/label-queue/roi/{d.id}"

        items.append(
            QueueItem(
                id=d.id,
                roi_sha256=d.roi_sha256,
                created_at=d.created_at.isoformat(),
                image_url=img_url,
                metadata_json=d.metadata_json or "",
                is_withdrawn=bool(d.is_withdrawn),
                label_submissions=sub_count,
                already_labeled_by_me=already_by_me,
                conflict=False,
                conflict_detail={},
            )
        )
        if len(items) >= limit:
            break

    return QueueResp(items=items)

@router.get("/conflicts", response_model=QueueResp, dependencies=[read_dep])
def conflict_items(
    limit: int = 50,
    db: OrmSession = Depends(get_db),
    request: Request = None
):
    """
    Dedicated conflicts queue: items not finalized but currently in conflict
    (mixed skip/label, disagreement, no-overlap, etc).
    """
    limit = max(1, min(int(limit), 200))

    storage = get_storage()
    rows = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.is_(None))
        .order_by(asc(models.DonatedSample.created_at))
        .limit(limit * 6)
        .all()
    )

    admin_user = getattr(request.state, "admin_user", None)
    my_id = int(admin_user.id) if admin_user and int(getattr(admin_user, "id", 0)) > 0 else None

    out: list[QueueItem] = []
    for d in rows:
        cinfo = _conflict_reason(db, d.id)
        if not cinfo.get("conflict"):
            continue

        # show even if already labeled by me (useful for review), but flag it
        already_by_me = False
        if my_id is not None:
            exists = (
                db.query(models.DonatedSampleLabel.id)
                .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
                .filter(models.DonatedSampleLabel.admin_user_id == my_id)
                .first()
            )
            already_by_me = bool(exists)

        sub_count = int(
            (db.query(func.count(models.DonatedSampleLabel.id))
             .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
             .scalar() or 0)
        )

        if d.roi_image_path.startswith("s3://"):
            img_url = storage.presign_get_url(d.roi_image_path, expires_sec=900) or ""
        else:
            img_url = f"/v1/admin/label-queue/roi/{d.id}"

        out.append(
            QueueItem(
                id=d.id,
                roi_sha256=d.roi_sha256,
                created_at=d.created_at.isoformat(),
                image_url=img_url,
                metadata_json=d.metadata_json or "",
                is_withdrawn=bool(d.is_withdrawn),
                label_submissions=sub_count,
                already_labeled_by_me=already_by_me,
                conflict=True,
                conflict_detail=cinfo,
            )
        )
        if len(out) >= limit:
            break

    return QueueResp(items=out)

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

@router.get("/{donation_id}/review", response_model=ConflictReviewResp, dependencies=[read_dep])
def conflict_review(donation_id: int, db: OrmSession = Depends(get_db)):
    d = db.get(models.DonatedSample, int(donation_id))
    if not d or d.is_withdrawn:
        raise HTTPException(404, "Not found")
    if d.labels_json is not None:
        raise HTTPException(409, "Already finalized")

    cinfo = _conflict_reason(db, d.id)

    subs = (
        db.query(models.DonatedSampleLabel)
        .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
        .order_by(desc(models.DonatedSampleLabel.created_at))
        .all()
    )
    admin_ids = list({s.admin_user_id for s in subs})
    admins = {}
    if admin_ids:
        for u in db.query(models.AdminUser).filter(models.AdminUser.id.in_(admin_ids)).all():
            admins[u.id] = u.email

    # suggested final:
    suggested = None
    need_n = max(2, int(settings.LABEL_CONSENSUS_N))
    non_skip = _distinct_latest_submissions(subs, n=need_n, non_skip=True)
    if len(non_skip) >= 2:
        # even if conflict, we can provide a suggested median-of-up-to-N
        picked = non_skip[: min(len(non_skip), need_n)]
        g, r, meta = _consensus_from_n(picked)
        suggested = {"labels": g, "region_labels": r, "suggested_meta": meta}

    return ConflictReviewResp(
        donated_sample_id=d.id,
        roi_sha256=d.roi_sha256,
        created_at=d.created_at.isoformat(),
        metadata_json=d.metadata_json or "",
        conflict_detail=cinfo,
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
        suggested_final=suggested,
    )

# --------------------------
# Submit label/skip + finalize attempt
# --------------------------

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
        payload={"donated_sample_id": d.id, "roi_sha256": d.roi_sha256, "regions": list((payload.region_labels or {}).keys())},
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

# --------------------------
# IRR stats endpoint
# --------------------------

@router.get("/stats/irr", response_model=IRRResp, dependencies=[read_dep])
def irr_stats(
    days: int = Query(default=30, ge=1, le=3650),
    db: OrmSession = Depends(get_db),
):
    """
    Computes inter-rater reliability on raw submissions:
      - MAE and Pearson r over continuous 0..1 values (pairwise, 2 raters)
      - weighted kappa on 5-bin discretization (quadratic weights)
    Uses latest 2 distinct non-skip submissions per sample within window.
    """
    cutoff = datetime.utcnow() - timedelta(days=int(days))
    max_samples = int(settings.IRR_MAX_SAMPLES)

    # candidate samples with >=2 non-skip distinct labelers
    # We do a two-step approach:
    #  1) collect sample ids with submissions within cutoff
    sample_ids = (
        db.query(models.DonatedSampleLabel.donated_sample_id)
        .filter(models.DonatedSampleLabel.created_at >= cutoff)
        .filter(models.DonatedSampleLabel.is_skip == False)  # noqa: E712
        .group_by(models.DonatedSampleLabel.donated_sample_id)
        .having(func.count(func.distinct(models.DonatedSampleLabel.admin_user_id)) >= 2)
        .limit(max_samples)
        .all()
    )
    sample_ids = [int(x[0]) for x in sample_ids]

    if not sample_ids:
        return IRRResp(days=int(days), samples_used=0, consensus_n=int(settings.LABEL_CONSENSUS_N))

    # collect latest submissions for each sample
    global_pairs: Dict[str, List[Tuple[float, float]]] = {}
    region_pairs: Dict[str, List[Tuple[float, float]]] = {}
    kappa_global: Dict[str, List[Tuple[int, int]]] = {}
    kappa_region: Dict[str, List[Tuple[int, int]]] = {}

    for sid in sample_ids:
        subs = (
            db.query(models.DonatedSampleLabel)
            .filter(models.DonatedSampleLabel.donated_sample_id == sid)
            .filter(models.DonatedSampleLabel.created_at >= cutoff)
            .order_by(desc(models.DonatedSampleLabel.created_at))
            .all()
        )
        picked = _distinct_latest_submissions(subs, n=2, non_skip=True)
        if len(picked) < 2:
            continue
        a = _loads(picked[0].labels_json)
        b = _loads(picked[1].labels_json)

        la = a.get("labels") if isinstance(a.get("labels"), dict) else {}
        lb = b.get("labels") if isinstance(b.get("labels"), dict) else {}
        common = set(la.keys()) & set(lb.keys())
        for k in common:
            va = _float01(la.get(k))
            vb = _float01(lb.get(k))
            if va is None or vb is None:
                continue
            global_pairs.setdefault(k, []).append((va, vb))
            kappa_global.setdefault(k, []).append((_bin5(va), _bin5(vb)))

        ra = a.get("region_labels") if isinstance(a.get("region_labels"), dict) else {}
        rb = b.get("region_labels") if isinstance(b.get("region_labels"), dict) else {}
        r_common = set(ra.keys()) & set(rb.keys())
        for region in r_common:
            da = ra.get(region) if isinstance(ra.get(region), dict) else {}
            dbb = rb.get(region) if isinstance(rb.get(region), dict) else {}
            keys = set(da.keys()) & set(dbb.keys())
            for k in keys:
                va = _float01(da.get(k))
                vb = _float01(dbb.get(k))
                if va is None or vb is None:
                    continue
                rk = f"{region}.{k}"
                region_pairs.setdefault(rk, []).append((va, vb))
                kappa_region.setdefault(rk, []).append((_bin5(va), _bin5(vb)))

    def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
        n = len(xs)
        if n < 5:
            return None
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
        denx = sum((xs[i]-mx)**2 for i in range(n))
        deny = sum((ys[i]-my)**2 for i in range(n))
        den = (denx * deny) ** 0.5
        if den == 0:
            return None
        return num / den

    def mae(pairs: List[Tuple[float, float]]) -> Optional[float]:
        if len(pairs) < 5:
            return None
        return sum(abs(a-b) for a,b in pairs) / float(len(pairs))

    global_stats: List[IRRLabelStat] = []
    for k, pairs in sorted(global_pairs.items()):
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        kap_pairs = kappa_global.get(k, [])
        kap = _weighted_kappa_quadratic([x for x,_ in kap_pairs], [y for _,y in kap_pairs], k=5) if kap_pairs else None
        global_stats.append(
            IRRLabelStat(
                key=k,
                n_pairs=len(pairs),
                mae=mae(pairs),
                pearson_r=pearson(xs, ys),
                weighted_kappa_5bin=kap,
            )
        )

    region_stats: List[IRRLabelStat] = []
    for rk, pairs in sorted(region_pairs.items()):
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        kap_pairs = kappa_region.get(rk, [])
        kap = _weighted_kappa_quadratic([x for x,_ in kap_pairs], [y for _,y in kap_pairs], k=5) if kap_pairs else None
        region_stats.append(
            IRRLabelStat(
                key=rk,
                n_pairs=len(pairs),
                mae=mae(pairs),
                pearson_r=pearson(xs, ys),
                weighted_kappa_5bin=kap,
            )
        )

    return IRRResp(
        days=int(days),
        samples_used=len(sample_ids),
        consensus_n=int(settings.LABEL_CONSENSUS_N),
        global_stats=global_stats,
        region_stats=region_stats,
    )
