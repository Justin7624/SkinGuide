# services/trainer/jobs/nightly_labeler_snapshot.py

from __future__ import annotations

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.api.app import models

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
    rel = max(0.0, min(1.0, 1.0 - float(mae)))
    return 0.2 + 0.8 * rel  # [0.2..1.0]

def compute_metrics(db, *, window_days: int, min_samples: int, max_samples: int = 20000):
    cutoff = datetime.utcnow() - timedelta(days=int(window_days))

    donations = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.isnot(None))
        .filter(models.DonatedSample.labeled_at.isnot(None))
        .filter(models.DonatedSample.labeled_at >= cutoff)
        .order_by(models.DonatedSample.labeled_at.desc())
        .limit(int(max_samples))
        .all()
    )

    # email cache
    emails = {u.id: u.email for u in db.query(models.AdminUser).all()}

    sums: Dict[int, float] = {}
    counts: Dict[int, int] = {}

    for d in donations:
        final = _loads(d.labels_json or "{}")
        if final.get("skipped") is True:
            continue
        final_flat = _flatten_labels(final)

        cons = final.get("consensus") if isinstance(final.get("consensus"), dict) else {}
        frm = cons.get("from") if isinstance(cons.get("from"), list) else []
        admin_ids: List[int] = []
        for item in frm:
            if isinstance(item, dict) and "admin_user_id" in item:
                try:
                    admin_ids.append(int(item["admin_user_id"]))
                except Exception:
                    pass
        admin_ids = list({x for x in admin_ids if x > 0})
        if not admin_ids:
            continue

        for aid in admin_ids:
            sub = (
                db.query(models.DonatedSampleLabel)
                .filter(models.DonatedSampleLabel.donated_sample_id == d.id)
                .filter(models.DonatedSampleLabel.admin_user_id == aid)
                .filter(models.DonatedSampleLabel.is_skip == False)  # noqa: E712
                .order_by(models.DonatedSampleLabel.created_at.desc())
                .first()
            )
            if not sub:
                continue
            sj = _loads(sub.labels_json or "{}")
            sub_flat = _flatten_labels(sj)
            m = _mae_between(final_flat, sub_flat)
            if m is None:
                continue
            sums[aid] = sums.get(aid, 0.0) + float(m)
            counts[aid] = counts.get(aid, 0) + 1

    out = []
    for aid, n in counts.items():
        if n < int(min_samples):
            continue
        mae = sums.get(aid, 0.0) / float(n)
        rel = max(0.0, min(1.0, 1.0 - mae))
        w = _weight_from_mae(mae)
        out.append({
            "admin_user_id": int(aid),
            "admin_email": emails.get(aid),
            "n_samples": int(n),
            "mean_abs_error": float(mae),
            "reliability": float(rel),
            "weight": float(w),
        })

    return out

def main():
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("SKINGUIDE_DATABASE_URL")
    if not db_url:
        raise SystemExit("Missing DATABASE_URL env var")

    window_days = int(os.environ.get("LABELER_WINDOW_DAYS", "180"))
    min_samples = int(os.environ.get("LABELER_MIN_SAMPLES", "10"))

    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        metrics = compute_metrics(db, window_days=window_days, min_samples=min_samples)

        now = datetime.utcnow()
        for m in metrics:
            snap = models.LabelerReliabilitySnapshot(
                created_at=now,
                window_days=int(window_days),
                admin_user_id=int(m["admin_user_id"]),
                admin_email=m.get("admin_email"),
                n_samples=int(m["n_samples"]),
                mean_abs_error=float(m["mean_abs_error"]),
                reliability=float(m["reliability"]),
                weight=float(m["weight"]),
                details_json=json.dumps({"min_samples": min_samples}, ensure_ascii=False),
            )
            db.add(snap)

        db.commit()
        print(f"Inserted {len(metrics)} labeler snapshots (window_days={window_days}) at {now.isoformat()}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
