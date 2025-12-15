# services/trainer/trainer.py

import os
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import httpx
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
    def __init__(self, out_dim=K):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.head = nn.Linear(64, out_dim)

    def forward(self, x):
        x = self.net(x).view(x.size(0), -1)
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
    return (img.astype(np.float32) / 255.0)

def masked_mse(pred: torch.Tensor, target: torch.Tensor, mask: torch.Tensor, eps=1e-6) -> torch.Tensor:
    diff = ((pred - target) ** 2) * mask
    denom = mask.sum(dim=1).clamp_min(eps)
    return (diff.sum(dim=1) / denom).mean()

def fetch_labeled_rows(db_url: str) -> List[Dict]:
    engine = create_engine(db_url, pool_pre_ping=True)
    q = text("""
        SELECT roi_sha256, roi_image_path, labels_json
        FROM donated_samples
        WHERE labels_json IS NOT NULL
    """)
    out = []
    with engine.connect() as conn:
        for r in conn.execute(q).mappings():
            out.append(dict(r))
    return out

def build_dataset(rows: List[Dict]) -> List[Dict]:
    items = []
    for r in rows:
        try:
            payload = json.loads(r["labels_json"] or "{}")
        except Exception:
            continue
        labels = payload.get("labels") or {}
        fitz = payload.get("fitzpatrick")
        age = payload.get("age_band")

        y = np.zeros((K,), dtype=np.float32)
        m = np.zeros((K,), dtype=np.float32)
        any_label = False
        for i, k in enumerate(ATTRIBUTE_KEYS):
            if k in labels:
                try:
                    v = float(labels[k])
                except Exception:
                    continue
                v = max(0.0, min(1.0, v))
                y[i] = v
                m[i] = 1.0
                any_label = True
        if not any_label:
            continue

        items.append({
            "roi_sha256": r["roi_sha256"],
            "path": Path(r["roi_image_path"].replace("file://", "")) if str(r["roi_image_path"]).startswith("file://") else Path(r["roi_image_path"]),
            "y": y,
            "m": m,
            "fitzpatrick": fitz if fitz in FITZ else None,
            "age_band": age if age in AGE_BANDS else None,
        })
    return items

def split_idx(n: int, val_split: float, seed: int):
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    rng.shuffle(idx)
    split = int((1.0 - val_split) * n)
    return idx[:split].tolist(), idx[split:].tolist()

def iter_batches(lst: List[int], bs: int):
    for i in range(0, len(lst), bs):
        yield lst[i:i+bs]

def make_batch(items: List[Dict], batch: List[int], img_size: int):
    xs, ys, ms, meta = [], [], [], []
    for j in batch:
        it = items[j]
        x = load_image(it["path"], img_size)
        xs.append(x); ys.append(it["y"]); ms.append(it["m"]); meta.append(it)
    X = torch.from_numpy(np.stack(xs)).permute(0, 3, 1, 2)
    Y = torch.from_numpy(np.stack(ys))
    M = torch.from_numpy(np.stack(ms))
    return X, Y, M, meta

def slice_metrics(cache: List[Dict], key: str, allowed: List[str]) -> Dict[str, Dict]:
    groups: Dict[str, List[float]] = {a: [] for a in allowed}
    groups["unknown"] = []
    for ex in cache:
        g = ex.get(key)
        if g in groups:
            groups[g].append(ex["loss"])
        else:
            groups["unknown"].append(ex["loss"])

    out: Dict[str, Dict] = {}
    for g, vals in groups.items():
        if not vals:
            continue
        out[g] = {
            "n": int(len(vals)),
            "mean_loss": float(np.mean(vals)),
            "p50_loss": float(np.percentile(vals, 50)),
            "p90_loss": float(np.percentile(vals, 90)),
        }
    return out

def eval_model(model: nn.Module, items: List[Dict], idxs: List[int], device, img_size: int, bs: int):
    model.eval()
    losses = []
    cache = []
    with torch.no_grad():
        for b in iter_batches(idxs, bs):
            X, Y, M, meta = make_batch(items, b, img_size)
            X, Y, M = X.to(device), Y.to(device), M.to(device)
            pred = torch.sigmoid(model(X))
            # per example loss
            diff = ((pred - Y) ** 2) * M
            denom = M.sum(dim=1).clamp_min(1e-6)
            per_ex = (diff.sum(dim=1) / denom).detach().cpu().numpy()
            losses.append(float(masked_mse(pred, Y, M).detach().cpu().item()))
            for i, it in enumerate(meta):
                cache.append({
                    "loss": float(per_ex[i]),
                    "fitzpatrick": it.get("fitzpatrick"),
                    "age_band": it.get("age_band"),
                })
    return float(np.mean(losses)) if losses else 1e9, cache

async def publish_to_api(api_base: str, admin_key: str, version: str, model_path: Path, manifest_path: Path):
    # register
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{api_base}/v1/model/register",
            headers={"X-Admin-Key": admin_key},
            json={
                "version": version,
                "model_uri": f"file://{str(model_path)}",
                "manifest_uri": f"file://{str(manifest_path)}",
                "metrics_json": None,
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"register failed: {r.status_code} {r.text}")

        # activate
        r2 = await client.post(
            f"{api_base}/v1/model/activate",
            headers={"X-Admin-Key": admin_key},
            json={"version": version},
        )
        if r2.status_code >= 400:
            raise RuntimeError(f"activate failed: {r2.status_code} {r2.text}")

def main():
    db_url = os.getenv("TRAIN_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not db_url:
        print("Missing TRAIN_DATABASE_URL or DATABASE_URL")
        return

    api_base = os.getenv("API_BASE_URL", "http://api:8000")
    admin_key = os.getenv("ADMIN_API_KEY", "")
    do_publish = os.getenv("PUBLISH", "false").lower() == "true"

    img_size = env_int("IMG_SIZE", 128)
    epochs = env_int("EPOCHS", 8)
    bs = env_int("BATCH_SIZE", 16)
    val_split = env_float("VAL_SPLIT", 0.2)
    seed = env_int("SEED", 123)

    version = os.getenv("NEXT_MODEL_VERSION", f"0.5.{int(time.time())}")

    rows = fetch_labeled_rows(db_url)
    items = build_dataset(rows)
    if len(items) < 20:
        print(f"Not enough labeled samples to train (need ~20+, have {len(items)}).")
        return

    train_idx, val_idx = split_idx(len(items), val_split, seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = TinySkinNet().to(device)
    opt = optim.Adam(net.parameters(), lr=3e-4)

    best_val = 1e9
    best_state = None

    for ep in range(1, epochs + 1):
        net.train()
        losses = []
        for b in iter_batches(train_idx, bs):
            X, Y, M, _ = make_batch(items, b, img_size)
            X, Y, M = X.to(device), Y.to(device), M.to(device)
            pred = torch.sigmoid(net(X))
            loss = masked_mse(pred, Y, M)
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(float(loss.detach().cpu().item()))

        val_loss, _cache = eval_model(net, items, val_idx, device, img_size, bs)
        tr = float(np.mean(losses)) if losses else 1e9
        print(f"Epoch {ep}/{epochs} train={tr:.4f} val={val_loss:.4f}")

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}

    if best_state is not None:
        net.load_state_dict(best_state)

    final_val, cache = eval_model(net, items, val_idx, device, img_size, bs)
    fitz_s = slice_metrics(cache, "fitzpatrick", FITZ)
    age_s = slice_metrics(cache, "age_band", AGE_BANDS)

    artifacts_root = Path(os.getenv("MODEL_ARTIFACTS_DIR", "/models/artifacts"))
    out_dir = artifacts_root / version
    out_dir.mkdir(parents=True, exist_ok=True)

    net.eval()
    example = torch.zeros((1, 3, img_size, img_size), dtype=torch.float32).to(device)
    traced = torch.jit.trace(net, example)

    model_path = out_dir / "model.pt"
    traced.save(str(model_path))

    manifest = Manifest(
        version=version,
        trained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        total_labeled_rows=len(items),
        train_samples=len(train_idx),
        val_samples=len(val_idx),
        metrics={"val_masked_mse": float(final_val)},
        bias_slices={"fitzpatrick": fitz_s, "age_band": age_s},
        notes="DB-driven labels. Baseline model. Do not claim diagnosis.",
    )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.__dict__, indent=2), encoding="utf-8")

    print(f"Wrote {model_path}")
    print(f"Wrote {manifest_path}")

    if do_publish:
        if not admin_key:
            raise RuntimeError("PUBLISH=true requires ADMIN_API_KEY")
        import asyncio
        asyncio.run(publish_to_api(api_base, admin_key, version, model_path, manifest_path))
        print(f"Published + activated {version}")

if __name__ == "__main__":
    main()
