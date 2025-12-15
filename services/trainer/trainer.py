# services/trainer/trainer.py
#
# Trainer that consumes labels directly from Postgres (donated_samples.labels_json)
# and computes basic bias slices (Fitzpatrick + age band) on validation.
#
# Assumptions:
# - donated_samples.roi_image_path is accessible to this process (mount the same volume)
# - labels_json structure: {"labels": {...}, "fitzpatrick": "...", "age_band": "..."}
#
# Env:
#   DATABASE_URL or TRAIN_DATABASE_URL:
#       e.g. postgresql+psycopg://user:pass@host:5432/db
#   OUT_DIR: ./out (default)
#   NEXT_MODEL_VERSION: auto
#   EPOCHS: 8
#   BATCH_SIZE: 16
#   IMG_SIZE: 128
#   VAL_SPLIT: 0.2
#   SEED: 123

import os
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from sqlalchemy import create_engine, text

ATTRIBUTE_KEYS = [
    "uneven_tone_appearance",
    "hyperpigmentation_appearance",
    "redness_appearance",
    "texture_roughness_appearance",
    "shine_oiliness_appearance",
    "pore_visibility_appearance",
    "fine_lines_appearance",
    "dryness_flaking_appearance",
]
K = len(ATTRIBUTE_KEYS)

FITZ = ["I", "II", "III", "IV", "V", "VI"]
AGE_BANDS = ["<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]

@dataclass
class Manifest:
    version: str
    trained_at: str
    total_labeled_rows: int
    train_samples: int
    val_samples: int
    metrics: Dict[str, float]
    bias_slices: Dict[str, Dict]
    notes: str

class TinySkinNet(nn.Module):
    """
    Small CNN regression head. Output logits -> sigmoid -> [0..1] scores.
    """
    def __init__(self, out_dim=K):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 16, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.head = nn.Linear(64, out_dim)

    def forward(self, x):
        x = self.net(x)
        x = x.view(x.size(0), -1)
        return self.head(x)

def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

def load_image(path: Path, size: int) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Bad image: {path}")
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    return img

def masked_mse(pred: torch.Tensor, target: torch.Tensor, mask: torch.Tensor, eps=1e-6) -> torch.Tensor:
    diff = (pred - target) ** 2
    diff = diff * mask
    denom = mask.sum(dim=1).clamp_min(eps)
    per_ex = diff.sum(dim=1) / denom
    return per_ex.mean()

def masked_mae_per_attr(pred: torch.Tensor, target: torch.Tensor, mask: torch.Tensor, eps=1e-6) -> Dict[str, float]:
    # Computes MAE per attribute across all labeled elements
    absdiff = (pred - target).abs() * mask
    denom = mask.sum(dim=0).clamp_min(eps)
    mae = absdiff.sum(dim=0) / denom
    out = {}
    for i, k in enumerate(ATTRIBUTE_KEYS):
        out[f"val_mae_{k}"] = float(mae[i].detach().cpu().item())
    return out

def fetch_labeled_rows_from_db(db_url: str) -> List[Dict]:
    """
    Returns rows with:
      roi_sha256, roi_image_path, labels_json, metadata_json
    Only rows with labels_json IS NOT NULL are returned.
    """
    engine = create_engine(db_url, pool_pre_ping=True)
    q = text("""
        SELECT roi_sha256, roi_image_path, labels_json, metadata_json
        FROM donated_samples
        WHERE labels_json IS NOT NULL
    """)
    rows = []
    with engine.connect() as conn:
        res = conn.execute(q)
        for r in res.mappings():
            rows.append({
                "roi_sha256": r["roi_sha256"],
                "roi_image_path": r["roi_image_path"],
                "labels_json": r["labels_json"],
                "metadata_json": r["metadata_json"],
            })
    return rows

def build_dataset(rows: List[Dict]) -> List[Dict]:
    """
    Builds dataset list where each item:
      {
        "path": Path,
        "y": np.float32[K],
        "m": np.float32[K],
        "fitzpatrick": Optional[str],
        "age_band": Optional[str],
        "roi_sha256": str
      }
    Sparse labels supported via mask m.
    """
    data = []
    for row in rows:
        img_path = row.get("roi_image_path")
        roi_sha = row.get("roi_sha256") or ""
        if not img_path or not roi_sha:
            continue

        try:
            labels_payload = json.loads(row.get("labels_json") or "{}")
        except Exception:
            continue

        labels = labels_payload.get("labels") or {}
        fitz = labels_payload.get("fitzpatrick")
        age = labels_payload.get("age_band")

        y = np.zeros((K,), dtype=np.float32)
        m = np.zeros((K,), dtype=np.float32)

        any_label = False
        for i, key in enumerate(ATTRIBUTE_KEYS):
            if key in labels:
                try:
                    v = float(labels[key])
                except Exception:
                    continue
                v = max(0.0, min(1.0, v))
                y[i] = v
                m[i] = 1.0
                any_label = True

        if not any_label:
            continue

        data.append({
            "path": Path(img_path),
            "y": y,
            "m": m,
            "fitzpatrick": fitz if fitz in FITZ else None,
            "age_band": age if age in AGE_BANDS else None,
            "roi_sha256": roi_sha,
        })
    return data

def split_dataset(n: int, val_split: float, seed: int):
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    rng.shuffle(idx)
    split = int((1.0 - val_split) * n)
    train_idx = idx[:split]
    val_idx = idx[split:]
    return train_idx.tolist(), val_idx.tolist()

def make_batch(items: List[Dict], indices: List[int], img_size: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, List[Dict]]:
    xs, ys, ms = [], [], []
    meta = []
    for j in indices:
        it = items[int(j)]
        x = load_image(it["path"], size=img_size)
        xs.append(x)
        ys.append(it["y"])
        ms.append(it["m"])
        meta.append(it)

    X = torch.from_numpy(np.stack(xs)).permute(0, 3, 1, 2)  # NCHW
    Y = torch.from_numpy(np.stack(ys))
    M = torch.from_numpy(np.stack(ms))
    return X, Y, M, meta

def iter_batches(lst: List[int], batch_size: int):
    for i in range(0, len(lst), batch_size):
        yield lst[i:i + batch_size]

def eval_on_indices(
    model: nn.Module,
    items: List[Dict],
    indices: List[int],
    device: torch.device,
    img_size: int,
    batch_size: int,
) -> Tuple[float, Dict[str, float], List[Dict]]:
    """
    Returns:
      masked_mse, per_attr_mae_dict, val_cache list with entries:
        {
          "fitzpatrick": ...,
          "age_band": ...,
          "loss": float,
          "mask_sum": int,
          "roi_sha256": ...
        }
    """
    model.eval()
    losses = []
    all_preds = []
    all_targs = []
    all_masks = []
    cache = []

    with torch.no_grad():
        for b in iter_batches(indices, batch_size):
            X, Y, M, meta = make_batch(items, b, img_size)
            X, Y, M = X.to(device), Y.to(device), M.to(device)
            pred = torch.sigmoid(model(X))
            loss = masked_mse(pred, Y, M)
            losses.append(float(loss.detach().cpu().item()))

            all_preds.append(pred.detach().cpu())
            all_targs.append(Y.detach().cpu())
            all_masks.append(M.detach().cpu())

            # cache per-example loss for slices
            # compute per-example masked mse
            diff = ((pred - Y) ** 2) * M
            denom = M.sum(dim=1).clamp_min(1e-6)
            per_ex = (diff.sum(dim=1) / denom).detach().cpu().numpy()

            for i, it in enumerate(meta):
                cache.append({
                    "fitzpatrick": it.get("fitzpatrick"),
                    "age_band": it.get("age_band"),
                    "loss": float(per_ex[i]),
                    "mask_sum": int(np.sum(it.get("m", np.zeros((K,), dtype=np.float32)) > 0)),
                    "roi_sha256": it.get("roi_sha256"),
                })

    val_loss = float(np.mean(losses)) if losses else 1e9
    P = torch.cat(all_preds, dim=0) if all_preds else torch.zeros((0, K))
    T = torch.cat(all_targs, dim=0) if all_targs else torch.zeros((0, K))
    MK = torch.cat(all_masks, dim=0) if all_masks else torch.zeros((0, K))
    per_attr = masked_mae_per_attr(P, T, MK) if P.shape[0] else {}
    return val_loss, per_attr, cache

def slice_metrics(cache: List[Dict], key: str, allowed: List[str]) -> Dict[str, Dict]:
    """
    cache contains per-example loss; slice by cache[key] in allowed.
    Returns dict like:
      {"I": {"n": 10, "mean_loss": 0.12}, ... , "unknown": {...}}
    """
    out: Dict[str, Dict] = {}
    groups: Dict[str, List[float]] = {a: [] for a in allowed}
    groups["unknown"] = []

    for ex in cache:
        g = ex.get(key)
        if g in groups:
            groups[g].append(float(ex["loss"]))
        else:
            groups["unknown"].append(float(ex["loss"]))

    for g, vals in groups.items():
        if len(vals) == 0:
            continue
        out[g] = {
            "n": int(len(vals)),
            "mean_loss": float(np.mean(vals)),
            "p50_loss": float(np.percentile(vals, 50)),
            "p90_loss": float(np.percentile(vals, 90)),
        }
    return out

def main():
    db_url = os.getenv("TRAIN_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not db_url:
        print("Missing TRAIN_DATABASE_URL or DATABASE_URL")
        return

    out_dir = Path(os.getenv("OUT_DIR", "./out"))
    out_dir.mkdir(parents=True, exist_ok=True)

    version = os.getenv("NEXT_MODEL_VERSION", f"0.4.{int(time.time())}")

    epochs = env_int("EPOCHS", 8)
    batch_size = env_int("BATCH_SIZE", 16)
    img_size = env_int("IMG_SIZE", 128)
    val_split = env_float("VAL_SPLIT", 0.2)
    seed = env_int("SEED", 123)

    rows = fetch_labeled_rows_from_db(db_url)
    items = build_dataset(rows)

    if len(items) < 20:
        print(f"Not enough labeled samples to train (need ~20+, have {len(items)}).")
        return

    train_idx, val_idx = split_dataset(len(items), val_split=val_split, seed=seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TinySkinNet(out_dim=K).to(device)

    opt = optim.Adam(model.parameters(), lr=3e-4)

    best_val = 1e9
    best_state = None

    train_list = train_idx
    val_list = val_idx

    for ep in range(1, epochs + 1):
        model.train()
        train_losses = []

        for b in iter_batches(train_list, batch_size):
            X, Y, M, _ = make_batch(items, b, img_size)
            X, Y, M = X.to(device), Y.to(device), M.to(device)

            logits = model(X)
            pred = torch.sigmoid(logits)
            loss = masked_mse(pred, Y, M)

            opt.zero_grad()
            loss.backward()
            opt.step()

            train_losses.append(float(loss.detach().cpu().item()))

        # Validation + cache for slices
        val_loss, val_per_attr_mae, val_cache = eval_on_indices(
            model=model,
            items=items,
            indices=val_list,
            device=device,
            img_size=img_size,
            batch_size=batch_size,
        )

        tr = float(np.mean(train_losses)) if train_losses else 1e9
        print(f"Epoch {ep}/{epochs} train={tr:.4f} val={val_loss:.4f}")

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    # Final evaluation (best model) for manifest + slices
    final_val_loss, final_val_mae, final_cache = eval_on_indices(
        model=model,
        items=items,
        indices=val_list,
        device=device,
        img_size=img_size,
        batch_size=batch_size,
    )

    fitz_slices = slice_metrics(final_cache, key="fitzpatrick", allowed=FITZ)
    age_slices = slice_metrics(final_cache, key="age_band", allowed=AGE_BANDS)

    # Export TorchScript
    model.eval()
    example = torch.zeros((1, 3, img_size, img_size), dtype=torch.float32).to(device)
    traced = torch.jit.trace(model, example)
    out_model = out_dir / "model.pt"
    traced.save(str(out_model))

    metrics = {"val_masked_mse": float(final_val_loss)}
    metrics.update(final_val_mae)

    manifest = Manifest(
        version=version,
        trained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        total_labeled_rows=len(items),
        train_samples=len(train_list),
        val_samples=len(val_list),
        metrics=metrics,
        bias_slices={
            "fitzpatrick": fitz_slices,
            "age_band": age_slices,
        },
        notes=(
            "Trained on ROI-only donations with sparse 0..1 labels loaded from Postgres. "
            "Bias slices are basic masked-MSE summaries on validation by self-reported groups."
        ),
    )

    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest.__dict__, f, indent=2)

    # Optional: write a compact slices-only file for dashboards
    with open(out_dir / "bias_slices.json", "w", encoding="utf-8") as f:
        json.dump(manifest.bias_slices, f, indent=2)

    print(f"Saved: {out_model}")
    print(f"Saved: {out_dir / 'manifest.json'}")
    print(f"Saved: {out_dir / 'bias_slices.json'}")

if __name__ == "__main__":
    main()
