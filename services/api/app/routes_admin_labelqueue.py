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
# JSON helpers
# --------------------------

def _loads(s: str) -> Dict[str, Any]:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}

def _dumps(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return json.dumps({"_unserializable": True, "repr": repr(payload)}, ensure_ascii=False)

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

def _pairwise_abs_diffs(values: List[float]) -> List[float]:
    diffs = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            diffs.append(abs(values[i] - values[j]))
    return diffs

def _distinct_latest_submissions(
    subs: list[models.DonatedSampleLabel],
    *,
    n: int,
    non_skip: bool
) -> list[models.DonatedSampleLabel]:
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

def _consensus_from_n(submissions: list[models.DonatedSampleLabel]) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]], Dict[str, Any]]:
    parsed = [_loads(s.labels_json) for s in submissions]
    N = len(parsed)
    agg = _mean if N == 2 else _median

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

def _thresholds_for_n(n: int) -> tuple[float, float]:
    if n >= 3:
        return float(settings.LABEL_MEAN_ABS_DIFF_MAX_N3), float(settings.LABEL_MAX_ABS_DIFF_MAX_N3)
    return float(settings.LABEL_MEAN_ABS_DIFF_MAX), float(settings.LABEL_MAX_ABS_DIFF_MAX)

# --------------------------
# Consensus artifact writer
# --------------------------

def _write_consensus_artifact(
    db: OrmSession,
    *,
    donated_sample_id: int,
    status: str,
    algorithm: str,
    detail: Dict[str, Any],
    used_submission_ids: list[int] | None,
    request: Request | None,
):
    admin_user = getattr(request.state, "admin_user", None) if request is not None else None
    admin_id = None
    admin_email = None
    if admin_user is not None:
        try:
            if int(getattr(admin_user, "id", 0)) > 0:
                admin_id = int(admin_user.id)
            admin_email = getattr(admin_user, "email", None)
        except Exception:
            pass

    request_id = None
    if request is not None:
        request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")

    art = models.ConsensusArtifact(
        donated_sample_id=int(donated_sample_id),
        created_at=datetime.utcnow(),
        status=status,
        algorithm=algorithm,
        computed_by_admin_user_id=admin_id,
        computed_by_admin_email=admin_email,
        request_id=request_id,
        artifact_json=_dumps(
            {
                "donated_sample_id": int(donated_sample_id),
                "status": status,
                "algorithm": algorithm,
                "used_submission_ids": used_submission_ids or [],
                "detail": detail,
                "created_at": datetime.utcnow().isoformat(),
            }
        ),
    )
    db.add(art)

# --------------------------
# State classifier: conflict vs escalation vs ready
# --------------------------

def _consensus_state(db: OrmSession, donation_id: int) -> Dict[str, Any]:
    """
    Returns a structured state dict:
      - mode: "skip" | "label"
      - conflict: bool (true => conflicts queue / admin review)
      - escalate: bool (true => needs 3rd labeler)
      - need_n: int
      - have_non_skip: int distinct
      - have_skip: int distinct
      - reason / meta
    """
    subs = (
        db.query(models.DonatedSampleLabel)
        .filter(models.DonatedSampleLabel.donated_sample_id == donation_id)
        .order_by(desc(models.DonatedSampleLabel.created_at))
        .all()
    )

    base_n = max(2, int(settings.LABEL_CONSENSUS_N))
    esc_n = max(3, int(settings.CONFLICT_ESCALATE_TO_N))

    non_skip_distinct = _distinct_latest_submissions(subs, n=1000, non_skip=True)
    skip_distinct = _distinct_latest_submissions(subs, n=1000, non_skip=False)
    have_non_skip = len(non_skip_distinct)
    have_skip = len(skip_distinct)

    # Mixed skip/label is a true conflict for review
    if have_non_skip > 0 and have_skip > 0:
        return {
            "mode": "mixed",
            "conflict": True,
            "escalate": False,
            "need_n": base_n,
            "have_non_skip": have_non_skip,
            "have_skip": have_skip,
            "reason": "mixed_skip_and_label",
        }

    # Pure skip path
    if have_skip >= base_n and have_non_skip == 0:
        return {
            "mode": "skip",
            "conflict": False,
            "escalate": False,
            "need_n": base_n,
            "have_non_skip": 0,
            "have_skip": have_skip,
            "ready": True,
        }

    # Not enough non-skip yet
    if have_non_skip < base_n:
        return {
            "mode": "label",
            "conflict": False,
            "escalate": False,
            "need_n": base_n,
            "have_non_skip": have_non_skip,
            "have_skip": 0,
            "ready": False,
            "reason": "need_more_labels",
        }

    # Evaluate base consensus using latest base_n distinct
    picked = _distinct_latest_submissions(subs, n=base_n, non_skip=True)
    g, r, meta = _consensus_from_n(picked)

    if meta.get("n_compared", 0) == 0:
        # no overlap keys is conflict; escalation might help
        if settings.CONFLICT_ESCALATE_ENABLED and have_non_skip < esc_n:
            return {
                "mode": "label",
                "conflict": False,
                "escalate": True,
                "need_n": esc_n,
                "have_non_skip": have_non_skip,
                "have_skip": 0,
                "reason": "no_overlap_keys_escalate",
                "meta": meta,
            }
        return {
            "mode": "label",
            "conflict": True,
            "escalate": False,
            "need_n": base_n,
            "have_non_skip": have_non_skip,
            "have_skip": 0,
            "reason": "no_overlap_keys",
            "meta": meta,
        }

    mean_max, abs_max = _thresholds_for_n(base_n)
    if float(meta.get("mean_abs_diff", 0.0)) > mean_max or float(meta.get("max_abs_diff", 0.0)) > abs_max:
        # Disagreement conflict: auto-escalate to third labeler when enabled (and not enough yet)
        if settings.CONFLICT_ESCALATE_ENABLED and have_non_skip < esc_n:
            return {
                "mode": "label",
                "conflict": False,
                "escalate": True,
                "need_n": esc_n,
                "have_non_skip": have_non_skip,
                "have_skip": 0,
                "reason": "disagreement_escalate_to_third",
                "meta": meta,
                "preview": {"labels": g, "region_labels": r},
            }

        # If already have >= esc_n, try N=esc_n finalize instead of conflict (median-of-3)
        if settings.CONFLICT_ESCALATE_ENABLED and have_non_skip >= esc_n:
            picked3 = _distinct_latest_submissions(subs, n=esc_n, non_skip=True)
            g3, r3, meta3 = _consensus_from_n(picked3)
            mean3, max3 = _thresholds_for_n(esc_n)
            if meta3.get("n_compared", 0) > 0 and float(meta3.get("mean_abs_diff", 0.0)) <= mean3 and float(meta3.get("max_abs_diff", 0.0)) <= max3:
                return {
                    "mode": "label",
                    "conflict": False,
                    "escalate": False,
                    "need_n": esc_n,
                    "have_non_skip": have_non_skip,
                    "have_skip": 0,
                    "ready": True,
                    "meta": meta3,
                    "preview": {"labels": g3, "region_labels": r3},
                    "used_n": esc_n,
                }

        return {
            "mode": "label",
            "conflict": True,
            "escalate": False,
            "need_n": base_n,
            "have_non_skip": have_non_skip,
            "have_skip": 0,
            "reason": "disagreement_conflict",
            "meta": meta,
            "preview": {"labels": g, "region_labels": r},
        }

    # Base consensus OK
    return {
        "mode": "label",
        "conflict": False,
        "escalate": False,
        "need_n": base_n,
        "have_non_skip": have_non_skip,
        "have_skip": 0,
        "ready": True,
        "meta": meta,
        "preview": {"labels": g, "region_labels": r},
        "used_n": base_n,
    }

def _finalize_if_ready(db: OrmSession, donation: models.DonatedSample, request: Request | None) -> Dict[str, Any]:
    if donation.labels_json is not None:
        return {"finalized": True, "reason": "already_final"}

    state = _consensus_state(db, donation.id)

    # Persist an artifact for every finalize attempt decision
    _write_consensus_artifact(
        db,
        donated_sample_id=donation.id,
        status=("finalized" if state.get("ready") else ("escalated" if state.get("escalate") else ("conflict" if state.get("conflict") else "needs_more"))),
        algorithm="median/mean_consensus",
        detail=state,
        used_submission_ids=[],
        request=request,
    )

    if not state.get("ready"):
        return {"finalized": False, **state}

    subs = (
        db.query(models.DonatedSampleLabel)
        .filter(models.DonatedSampleLabel.donated_sample_id == donation.id)
        .order_by(desc(models.DonatedSampleLabel.created_at))
        .all()
    )

    # skip consensus
    if state.get("mode") == "skip":
        need_n = int(state.get("need_n", 2))
        picked = _distinct_latest_submissions(subs, n=need_n, non_skip=False)
        donation.labels_json = _dumps(
            {
                "skipped": True,
                "reason": "consensus_skip",
                "consensus": {
                    "method": f"{need_n}_distinct_labelers_skip",
                    "from": [{"admin_user_id": s.admin_user_id, "submission_id": s.id, "created_at": s.created_at.isoformat()} for s in picked],
                },
                "finalized_at": datetime.utcnow().isoformat(),
            }
        )
        donation.labeled_at = datetime.utcnow()
        db.add(donation)

        _write_consensus_artifact(
            db,
            donated_sample_id=donation.id,
            status="skipped_final",
            algorithm="skip_consensus",
            detail={"need_n": need_n},
            used_submission_ids=[s.id for s in picked],
            request=request,
        )
        return {"finalized": True, "reason": "consensus_skip", "used_n": need_n}

    # label consensus
    used_n = int(state.get("used_n") or state.get("need_n") or max(2, int(settings.LABEL_CONSENSUS_N)))
    picked = _distinct_latest_submissions(subs, n=used_n, non_skip=True)
    g, r, meta = _consensus_from_n(picked)

    parsed = [_loads(s.labels_json) for s in picked]
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
            "method": (meta.get("aggregation") or "mean") + f"_of_{used_n}_distinct_labelers",
            "meta": meta,
            "from": [{"admin_user_id": s.admin_user_id, "submission_id": s.id, "created_at": s.created_at.isoformat()} for s in picked],
        },
        "finalized_at": datetime.utcnow().isoformat(),
    }

    donation.labels_json = _dumps(final)
    donation.labeled_at = datetime.utcnow()
    db.add(donation)

    _write_consensus_artifact(
        db,
        donated_sample_id=donation.id,
        status="finalized",
        algorithm="median/mean_consensus",
        detail={"used_n": used_n, "meta": meta},
        used_submission_ids=[s.id for s in picked],
        request=request,
    )

    return {"finalized": True, "reason": "consensus_ok", "used_n": used_n, "meta": meta}

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
    escalate: bool = False
    need_n: int = 2
    have_non_skip: int = 0
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

class LabelerStat(BaseModel):
    admin_user_id: int
    admin_email: str | None = None
    n_samples: int
    mean_abs_error: float | None = None
    reliability: float | None = None
    weight: float | None = None

class LabelerStatsResp(BaseModel):
    days: int
    min_samples: int
    items: list[LabelerStat] = Field(default_factory=list)

# --------------------------
# Queue endpoints
# --------------------------

@router.get("/next", response_model=QueueResp, dependencies=[read_dep])
def next_items(limit: int = 20, db: OrmSession = Depends(get_db), request: Request = None):
    """
    Normal queue excludes true conflicts, but includes 'escalate' items (needs 3rd labeler).
    """
    limit = max(1, min(int(limit), 100))
    admin_user = getattr(request.state, "admin_user", None)
    my_id = int(admin_user.id) if admin_user and int(getattr(admin_user, "id", 0)) > 0 else None

    fetch_n = limit * 6
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
        state = _consensus_state(db, d.id)
        if state.get("conflict"):
            continue  # true conflicts go to /conflicts

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
                escalate=bool(state.get("escalate")),
                need_n=int(state.get("need_n", 2)),
                have_non_skip=int(state.get("have_non_skip", 0)),
                conflict_detail=state,
            )
        )
        if len(items) >= limit:
            break

    return QueueResp(items=items)

@router.get("/conflicts", response_model=QueueResp, dependencies=[read_dep])
def conflict_items(limit: int = 50, db: OrmSession = Depends(get_db), request: Request = None):
    """
    True conflicts: mixed skip/label OR disagreement after escalation threshold met (or escalation disabled).
    """
    limit = max(1, min(int(limit), 200))

    storage = get_storage()
    rows = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.is_(None))
        .order_by(asc(models.DonatedSample.created_at))
        .limit(limit * 10)
        .all()
    )

    admin_user = getattr(request.state, "admin_user", None)
    my_id = int(admin_user.id) if admin_user and int(getattr(admin_user, "id", 0)) > 0 else None

    out: list[QueueItem] = []
    for d in rows:
        state = _consensus_state(db, d.id)
        if not state.get("conflict"):
            continue

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
                escalate=False,
                need_n=int(state.get("need_n", 2)),
                have_non_skip=int(state.get("have_non_skip", 0)),
                conflict_detail=state,
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

# --------------------------
# Label submit + skip + force finalize
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
        labels_json=_dumps(submission),
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
    finalize_info = _finalize_if_ready(db, d, request)

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
        labels_json=_dumps(submission),
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
    finalize_info = _finalize_if_ready(db, d, request)

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

    d.labels_json = _dumps(
        {
            **payload.final,
            "finalized_at": datetime.utcnow().isoformat(),
            "finalized_by": getattr(getattr(request.state, "admin_user", None), "email", None),
            "finalized_via": "force_finalize",
        }
    )
    d.labeled_at = datetime.utcnow()
    db.add(d)

    _write_consensus_artifact(
        db,
        donated_sample_id=d.id,
        status="finalized",
        algorithm="force_finalize",
        detail={"note": "admin override"},
        used_submission_ids=[],
        request=request,
    )

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
# Labeler reliability stats (for trainer weighting)
# --------------------------

def _flatten_labels(j: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    labels = j.get("labels") if isinstance(j.get("labels"), dict) else {}
    for k, v in labels.items():
        fv = _float01(v)
        if fv is not None:
            out[f"g:{k}"] = fv

    regions = j.get("region_labels") if isinstance(j.get("region_labels"), dict) else {}
    for region, d in regions.items():
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            fv = _float01(v)
            if fv is not None:
                out[f"r:{region}:{k}"] = fv
    return out

def _mae_between(a: Dict[str, float], b: Dict[str, float]) -> Optional[float]:
    keys = set(a.keys()) & set(b.keys())
    if not keys:
        return None
    return sum(abs(a[k] - b[k]) for k in keys) / float(len(keys))

def _weight_from_mae(mae: float) -> float:
    # reliability: 1 - MAE; weight range [0.2, 1.0]
    rel = max(0.0, min(1.0, 1.0 - float(mae)))
    return 0.2 + 0.8 * rel

@router.get("/stats/labelers", response_model=LabelerStatsResp, dependencies=[read_dep])
def labeler_stats(
    days: int = Query(default=180, ge=7, le=3650),
    min_samples: int = Query(default=10, ge=1, le=5000),
    db: OrmSession = Depends(get_db),
):
    """
    Computes per-labeler MAE against finalized consensus for samples they participated in.
    Trainer can use this endpoint OR replicate logic in-service.
    """
    cutoff = datetime.utcnow() - timedelta(days=int(days))

    # Finalized samples in window
    donations = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.isnot(None))
        .filter(models.DonatedSample.labeled_at.isnot(None))
        .filter(models.DonatedSample.labeled_at >= cutoff)
        .order_by(desc(models.DonatedSample.labeled_at))
        .limit(20000)
        .all()
    )

    # Accumulate per admin
    sums: Dict[int, float] = {}
    counts: Dict[int, int] = {}
    emails: Dict[int, str] = {}

    # cache admin emails
    for u in db.query(models.AdminUser).all():
        emails[u.id] = u.email

    for d in donations:
        try:
            final = json.loads(d.labels_json or "{}")
        except Exception:
            continue
        final_flat = _flatten_labels(final)
        cons = final.get("consensus") if isinstance(final.get("consensus"), dict) else {}
        frm = cons.get("from") if isinstance(cons.get("from"), list) else []
        admin_ids = []
        for item in frm:
            if isinstance(item, dict) and "admin_user_id" in item:
                try:
                    admin_ids.append(int(item["admin_user_id"]))
                except Exception:
                    pass
        admin_ids = list({x for x in admin_ids if x > 0})
        if not admin_ids:
            continue

        # Compare each admin's submission to final
        for aid in admin_ids:
            sub = (
                db.query(models.DonatedSampleLabel)
                .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
                .filter(models.DonatedSampleLabel.admin_user_id == aid)
                .filter(models.DonatedSampleLabel.is_skip == False)  # noqa: E712
                .order_by(desc(models.DonatedSampleLabel.created_at))
                .first()
            )
            if not sub:
                continue
            try:
                sj = json.loads(sub.labels_json or "{}")
            except Exception:
                continue
            sub_flat = _flatten_labels(sj)
            m = _mae_between(final_flat, sub_flat)
            if m is None:
                continue
            sums[aid] = sums.get(aid, 0.0) + float(m)
            counts[aid] = counts.get(aid, 0) + 1

    items: list[LabelerStat] = []
    for aid, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        if n < int(min_samples):
            continue
        mae = sums.get(aid, 0.0) / float(n)
        rel = max(0.0, min(1.0, 1.0 - mae))
        items.append(
            LabelerStat(
                admin_user_id=aid,
                admin_email=emails.get(aid),
                n_samples=int(n),
                mean_abs_error=float(round(mae, 4)),
                reliability=float(round(rel, 4)),
                weight=float(round(_weight_from_mae(mae), 4)),
            )
        )

    return LabelerStatsResp(days=int(days), min_samples=int(min_samples), items=items)
