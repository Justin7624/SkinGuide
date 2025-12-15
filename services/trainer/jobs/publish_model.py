# services/trainer/jobs/publish_model.py

from __future__ import annotations

import os
import json
import shutil
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import torch
import torch.nn as nn

from PIL import Image

try:
    from torchvision import transforms
    from torchvision.models import resnet18
except Exception as e:
    raise SystemExit(f"torchvision required. Import error: {e}")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.api.app import models


def _loads(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
                if isinstance(v, dict):
                    out.append(v)
            except Exception:
                continue
    return out

def _float01(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if v != v:
            return None
        return max(0.0, min(1.0, v))
    except Exception:
        return None

def flatten_labels(obj: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    labels = obj.get("labels") if isinstance(obj.get("labels"), dict) else {}
    for k, v in labels.items():
        fv = _float01(v)
        if fv is not None:
            out[f"g:{k}"] = fv
    rlabels = obj.get("region_labels") if isinstance(obj.get("region_labels"), dict) else {}
    for region, d in rlabels.items():
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            fv = _float01(v)
            if fv is not None:
                out[f"r:{region}:{k}"] = fv
    return out

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def _build_model(out_dim: int) -> nn.Module:
    m = resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, out_dim)
    return m

def _ensure_local_img(path: str) -> Optional[str]:
    if not path:
        return None
    if path.startswith("s3://"):
        return None
    return path if os.path.exists(path) else None

def _masked_mae(pred: torch.Tensor, target: torch.Tensor, mask: torch.Tensor, eps: float = 1e-8) -> torch.Tensor:
    # [K] each
    diff = (pred - target).abs() * mask
    denom = mask.sum().clamp_min(eps)
    return diff.sum() / denom

def _slice_key(row: Dict[str, Any]) -> Tuple[str, str]:
    # bias slices: fitzpatrick and age_band (from consensus labels_json if available in dataset row)
    fitz = row.get("fitzpatrick") or "unknown"
    age = row.get("age_band") or "unknown"
    return str(fitz), str(age)

def evaluate_bias_slices(
    *,
    model: nn.Module,
    device: torch.device,
    manifest: Dict[str, Any],
    dataset_rows: List[Dict[str, Any]],
    image_size: int,
    max_rows: int = 20000,
) -> Dict[str, Any]:
    key_to_index = manifest.get("key_to_index") or {}
    label_keys = manifest.get("label_keys") or []
    if not isinstance(key_to_index, dict) or not label_keys:
        return {"error": "manifest missing key_to_index or label_keys"}

    K = len(label_keys)
    tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
    ])

    # simple holdout: last 15% of rows (consistent-ish)
    n = min(len(dataset_rows), max_rows)
    rows = dataset_rows[:n]
    split = int(n * 0.85)
    val = rows[split:] if split < n else rows

    overall = {"n": 0, "mae_sum": 0.0}
    by_fitz: Dict[str, Dict[str, Any]] = {}
    by_age: Dict[str, Dict[str, Any]] = {}
    by_combo: Dict[str, Dict[str, Any]] = {}

    model.eval()

    for r in val:
        imgp = _ensure_local_img(r.get("roi_image_path") or "")
        labels_obj = r.get("labels") if isinstance(r.get("labels"), dict) else {}
        flat = flatten_labels(labels_obj)
        if not imgp or not flat:
            continue

        # build target/mask
        y = torch.zeros(K, dtype=torch.float32)
        m = torch.zeros(K, dtype=torch.float32)
        for k, v in flat.items():
            idx = key_to_index.get(k)
            if idx is None:
                continue
            y[int(idx)] = float(v)
            m[int(idx)] = 1.0
        if float(m.sum().item()) <= 0:
            continue

        im = Image.open(imgp).convert("RGB")
        x = tf(im).unsqueeze(0).to(device)  # [1,3,H,W]

        with torch.no_grad():
            pred = model(x).detach().float().cpu().view(-1)
        pred = pred.clamp(0.0, 1.0)

        mae = float(_masked_mae(pred, y, m).item())

        overall["n"] += 1
        overall["mae_sum"] += mae

        fitz, age = _slice_key(r)

        def bump(bucket: Dict[str, Dict[str, Any]], key: str):
            if key not in bucket:
                bucket[key] = {"n": 0, "mae_sum": 0.0}
            bucket[key]["n"] += 1
            bucket[key]["mae_sum"] += mae

        bump(by_fitz, fitz)
        bump(by_age, age)
        bump(by_combo, f"{fitz}|{age}")

    def finalize(d: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        out = {}
        for k, v in d.items():
            n = int(v["n"])
            out[k] = {
                "n": n,
                "mae": (float(v["mae_sum"]) / n) if n else None
            }
        return out

    return {
        "overall_val": {
            "n": int(overall["n"]),
            "mae": (overall["mae_sum"] / overall["n"]) if overall["n"] else None
        },
        "by_fitzpatrick": finalize(by_fitz),
        "by_age_band": finalize(by_age),
        "by_fitz_age": finalize(by_combo),
    }

def make_model_card_md(
    *,
    version: str,
    created_at: str,
    manifest: Dict[str, Any],
    metrics: Dict[str, Any],
    bias: Dict[str, Any],
    dataset_path: str,
    model_sha256: str,
) -> str:
    keys = manifest.get("label_keys") or []
    img_size = manifest.get("image_size") or 224
    best = metrics.get("best_val_loss", None)

    def fmt(v):
        return "—" if v is None else f"{v:.6f}" if isinstance(v, (int, float)) else str(v)

    lines = []
    lines.append(f"# SkinGuide Model Card — {version}")
    lines.append("")
    lines.append(f"**Created:** {created_at}")
    lines.append(f"**Model SHA256:** `{model_sha256}`")
    lines.append(f"**Image size:** {img_size}")
    lines.append(f"**Outputs:** {len(keys)}")
    lines.append(f"**Trainer best_val_loss:** {fmt(best)}")
    lines.append("")
    lines.append("## Intended use")
    lines.append("- Cosmetic/skin **appearance guidance** (not medical diagnosis).")
    lines.append("- Provides **screening-style** suggestions and education; users should consult a clinician for diagnosis/treatment.")
    lines.append("")
    lines.append("## Data & labeling")
    lines.append(f"- Dataset source: `{dataset_path}`")
    lines.append("- Ground truth: **consensus labels** from the admin labeling workflow (2–3 labelers, conflict resolution).")
    lines.append("")
    lines.append("## Bias / slice checks (validation MAE)")
    ov = (bias.get("overall_val") or {})
    lines.append(f"- Overall val: n={ov.get('n','—')} · MAE={fmt(ov.get('mae'))}")
    lines.append("")
    lines.append("### By Fitzpatrick")
    bf = bias.get("by_fitzpatrick") or {}
    for k in sorted(bf.keys()):
        lines.append(f"- {k}: n={bf[k].get('n')} · MAE={fmt(bf[k].get('mae'))}")
    lines.append("")
    lines.append("### By age band")
    ba = bias.get("by_age_band") or {}
    for k in sorted(ba.keys()):
        lines.append(f"- {k}: n={ba[k].get('n')} · MAE={fmt(ba[k].get('mae'))}")
    lines.append("")
    lines.append("## Limitations / cautions")
    lines.append("- Image quality, lighting, makeup, filters, occlusion, and camera differences can degrade outputs.")
    lines.append("- The model predicts **appearance scores** (0–1) for a limited set of concerns; it does not detect cancers or diagnose disease.")
    lines.append("- Slice checks are **not** a guarantee of fairness; continue monitoring and expand representation.")
    lines.append("")
    lines.append("## Change log")
    lines.append("- This artifact was registered via `publish_model.py` (trainer job).")
    lines.append("")
    return "\n".join(lines)

def main():
    # Required
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("SKINGUIDE_DATABASE_URL")
    if not db_url:
        raise SystemExit("Missing DATABASE_URL env var")

    train_out = os.environ.get("TRAIN_OUT_DIR", "/mnt/data/model_out")
    model_pt = os.path.join(train_out, "model.pt")
    manifest_path = os.path.join(train_out, "manifest.json")
    if not (os.path.exists(model_pt) and os.path.exists(manifest_path)):
        raise SystemExit(f"TRAIN_OUT_DIR missing model.pt/manifest.json: {train_out}")

    # Optional: dataset jsonl used for slice eval + card
    dataset_jsonl = os.environ.get("TRAIN_JSONL_PATH", "/mnt/data/train_dataset.jsonl")

    # Where to store published artifacts (local registry)
    registry_dir = os.environ.get("MODEL_REGISTRY_DIR", "/mnt/data/model_registry")
    os.makedirs(registry_dir, exist_ok=True)

    # Version
    version = os.environ.get("MODEL_VERSION")
    if not version:
        version = datetime.utcnow().strftime("v%Y%m%d_%H%M%S")

    activate = os.environ.get("MODEL_AUTO_ACTIVATE", "0") == "1"

    manifest = _loads(manifest_path)
    image_size = int(manifest.get("image_size") or 224)
    keys = manifest.get("label_keys") or []
    if not keys:
        raise SystemExit("manifest.json missing label_keys")

    # Load model to compute bias slices
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _build_model(len(keys))
    state = torch.load(model_pt, map_location="cpu")
    model.load_state_dict(state, strict=True)
    model.to(device)
    model.eval()

    rows = _read_jsonl(dataset_jsonl) if os.path.exists(dataset_jsonl) else []
    bias = evaluate_bias_slices(
        model=model,
        device=device,
        manifest=manifest,
        dataset_rows=rows,
        image_size=image_size,
        max_rows=int(os.environ.get("MODEL_CARD_MAX_ROWS", "20000")),
    )

    model_sha = _sha256_file(model_pt)

    # metrics_json in DB (keep small)
    metrics_json = {
        "best_val_loss": manifest.get("best_val_loss"),
        "n_outputs": len(keys),
        "image_size": image_size,
        "bias_overall_mae": (bias.get("overall_val") or {}).get("mae"),
        "bias_overall_n": (bias.get("overall_val") or {}).get("n"),
    }

    created_at = datetime.utcnow().isoformat()
    card_md = make_model_card_md(
        version=version,
        created_at=created_at,
        manifest=manifest,
        metrics=metrics_json,
        bias=bias,
        dataset_path=dataset_jsonl if os.path.exists(dataset_jsonl) else "unknown",
        model_sha256=model_sha,
    )

    # Publish to local registry (versioned folder)
    out_dir = os.path.join(registry_dir, version)
    os.makedirs(out_dir, exist_ok=True)

    pub_model = os.path.join(out_dir, "model.pt")
    pub_manifest = os.path.join(out_dir, "manifest.json")
    pub_card = os.path.join(out_dir, "model_card.md")
    pub_bias = os.path.join(out_dir, "bias_slices.json")

    shutil.copy2(model_pt, pub_model)
    shutil.copy2(manifest_path, pub_manifest)
    with open(pub_card, "w", encoding="utf-8") as f:
        f.write(card_md)
    with open(pub_bias, "w", encoding="utf-8") as f:
        json.dump(bias, f, ensure_ascii=False, indent=2)

    # Register in DB
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        exists = db.query(models.ModelArtifact).filter(models.ModelArtifact.version == version).first()
        if exists:
            raise SystemExit(f"ModelArtifact version already exists: {version}")

        if activate:
            db.query(models.ModelArtifact).filter(models.ModelArtifact.is_active == True).update({"is_active": False})  # noqa: E712

        rec = models.ModelArtifact(
            created_at=datetime.utcnow(),
            version=version,
            model_uri=pub_model,
            manifest_uri=pub_manifest,
            model_card_uri=pub_card,
            metrics_json=json.dumps(metrics_json, ensure_ascii=False),
            is_active=bool(activate),
        )
        db.add(rec)
        db.commit()

        print(f"Registered ModelArtifact: version={version} active={activate}")
        print(f"  model_uri={pub_model}")
        print(f"  manifest_uri={pub_manifest}")
        print(f"  model_card_uri={pub_card}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
