# services/trainer/train_from_db.py

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import API models
# Assumes trainer container has services/api on PYTHONPATH (or package install)
from services.api.app import models
from services.api.app.db import Base

@dataclass
class TrainRow:
    donated_sample_id: int
    roi_image_path: str
    labels: Dict[str, Any]          # includes "labels" + "region_labels"
    sample_weight: float
    meta: Dict[str, Any]

def _loads(s: str) -> Dict[str, Any]:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}

def _flatten_labels(j: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    labels = j.get("labels") if isinstance(j.get("labels"), dict) else {}
    for k, v in labels.items():
        try:
            fv = float(v)
        except Exception:
            continue
        if fv != fv:
            continue
        fv = max(0.0, min(1.0, fv))
        out[f"g:{k}"] = fv

    regions = j.get("region_labels") if isinstance(j.get("region_labels"), dict) else {}
    for region, d in regions.items():
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            try:
                fv = float(v)
            except Exception:
                continue
            if fv != fv:
                continue
            fv = max(0.0, min(1.0, fv))
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

def compute_labeler_weights(db, *, max_samples: int = 20000, min_samples: int = 10) -> Dict[int, float]:
    """
    Labeler reliability computed as MAE(submission vs final consensus) averaged across samples.
    Returns admin_user_id -> weight.
    """
    donations = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.isnot(None))
        .filter(models.DonatedSample.labeled_at.isnot(None))
        .order_by(models.DonatedSample.labeled_at.desc())
        .limit(int(max_samples))
        .all()
    )

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

    weights: Dict[int, float] = {}
    for aid, n in counts.items():
        if n < int(min_samples):
            continue
        mae = sums.get(aid, 0.0) / float(n)
        weights[aid] = _weight_from_mae(mae)

    return weights

def sample_weight_for_final(final: Dict[str, Any], labeler_weights: Dict[int, float]) -> float:
    cons = final.get("consensus") if isinstance(final.get("consensus"), dict) else {}
    frm = cons.get("from") if isinstance(cons.get("from"), list) else []
    admin_ids: List[int] = []
    for item in frm:
        if isinstance(item, dict) and "admin_user_id" in item:
            try:
                admin_ids.append(int(item["admin_user_id"]))
            except Exception:
                pass
    admin_ids = [x for x in admin_ids if x > 0]
    if not admin_ids:
        return 1.0

    ws = []
    for aid in admin_ids:
        ws.append(float(labeler_weights.get(aid, 1.0)))
    if not ws:
        return 1.0
    return sum(ws) / float(len(ws))

def build_training_rows(db, *, limit: int = 50000, labeler_weights: Dict[int, float]) -> List[TrainRow]:
    rows: List[TrainRow] = []
    donations = (
        db.query(models.DonatedSample)
        .filter(models.DonatedSample.is_withdrawn == False)  # noqa: E712
        .filter(models.DonatedSample.labels_json.isnot(None))
        .filter(models.DonatedSample.labeled_at.isnot(None))
        .order_by(models.DonatedSample.labeled_at.desc())
        .limit(int(limit))
        .all()
    )
    for d in donations:
        final = _loads(d.labels_json or "{}")
        if final.get("skipped") is True:
            continue

        w = sample_weight_for_final(final, labeler_weights)
        rows.append(
            TrainRow(
                donated_sample_id=int(d.id),
                roi_image_path=d.roi_image_path,
                labels={
                    "labels": final.get("labels") or {},
                    "region_labels": final.get("region_labels") or {},
                },
                sample_weight=float(w),
                meta={
                    "consensus": final.get("consensus") or {},
                    "labeled_at": d.labeled_at.isoformat() if d.labeled_at else None,
                },
            )
        )
    return rows

def write_jsonl(rows: List[TrainRow], out_path: str):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "donated_sample_id": r.donated_sample_id,
                "roi_image_path": r.roi_image_path,
                "labels": r.labels,
                "sample_weight": r.sample_weight,
                "meta": r.meta,
            }, ensure_ascii=False) + "\n")

def main():
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("SKINGUIDE_DATABASE_URL")
    if not db_url:
        raise SystemExit("Missing DATABASE_URL env var")

    out_path = os.environ.get("TRAIN_JSONL_PATH", "/mnt/data/train_dataset.jsonl")
    limit = int(os.environ.get("TRAIN_LIMIT", "50000"))
    min_samples = int(os.environ.get("LABELER_MIN_SAMPLES", "10"))

    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)

    db = SessionLocal()
    try:
        lw = compute_labeler_weights(db, max_samples=20000, min_samples=min_samples)
        rows = build_training_rows(db, limit=limit, labeler_weights=lw)
        write_jsonl(rows, out_path)
        print(f"Wrote {len(rows)} rows to {out_path}")
        print(f"Computed {len(lw)} labeler weights (min_samples={min_samples})")
    finally:
        db.close()

if __name__ == "__main__":
    main()
