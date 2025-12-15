# services/trainer/train_pytorch.py

from __future__ import annotations

import os
import json
import math
import random
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

from PIL import Image

try:
    from torchvision import transforms
    from torchvision.models import resnet18
except Exception as e:
    raise SystemExit(f"torchvision required for this trainer. Import error: {e}")

# ----------------------------
# Utilities
# ----------------------------

def _loads(line: str) -> Dict[str, Any]:
    try:
        v = json.loads(line)
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

def flatten_labels(obj: Dict[str, Any]) -> Dict[str, float]:
    """
    Flattens into a single key space:
      g:<key>
      r:<region>:<key>
    """
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

def ensure_local_path(path: str) -> Optional[str]:
    """
    For now: supports only local filesystem paths.
    If you store ROI as s3://... then mount/prefetch into local cache first.
    """
    if not path:
        return None
    if path.startswith("s3://"):
        return None
    return path

# ----------------------------
# Dataset
# ----------------------------

@dataclass
class Row:
    image_path: str
    flat: Dict[str, float]
    weight: float

class JsonlSkinDataset(Dataset):
    def __init__(self, rows: List[Row], key_to_idx: Dict[str, int], image_size: int = 224):
        self.rows = rows
        self.key_to_idx = key_to_idx
        self.K = len(key_to_idx)

        self.tf = transforms.Compose([
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),  # 0..1
        ])

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i: int):
        r = self.rows[i]
        img_path = ensure_local_path(r.image_path)
        if not img_path or (not os.path.exists(img_path)):
            # hard skip behavior: return a black image with zero mask; trainer will ignore via mask sum=0
            x = torch.zeros(3, 224, 224, dtype=torch.float32)
            y = torch.zeros(self.K, dtype=torch.float32)
            m = torch.zeros(self.K, dtype=torch.float32)
            w = torch.tensor(float(r.weight), dtype=torch.float32)
            return x, y, m, w

        im = Image.open(img_path).convert("RGB")
        x = self.tf(im)

        y = torch.zeros(self.K, dtype=torch.float32)
        m = torch.zeros(self.K, dtype=torch.float32)
        for k, v in r.flat.items():
            idx = self.key_to_idx.get(k)
            if idx is None:
                continue
            y[idx] = float(v)
            m[idx] = 1.0

        w = torch.tensor(float(r.weight), dtype=torch.float32)
        return x, y, m, w

# ----------------------------
# Model + Loss
# ----------------------------

class MultiRegressor(nn.Module):
    def __init__(self, out_dim: int):
        super().__init__()
        self.backbone = resnet18(weights=None)
        self.backbone.fc = nn.Linear(self.backbone.fc.in_features, out_dim)

    def forward(self, x):
        return self.backbone(x)

class WeightedMaskedMSE(nn.Module):
    def __init__(self, eps: float = 1e-8):
        super().__init__()
        self.eps = eps

    def forward(self, pred, target, mask, sample_weight):
        # pred/target/mask: [B,K], sample_weight: [B]
        diff2 = (pred - target) ** 2
        diff2 = diff2 * mask

        per_sample_sum = diff2.sum(dim=1)  # [B]
        per_sample_cnt = mask.sum(dim=1).clamp_min(0.0)  # [B]
        per_sample_mean = per_sample_sum / (per_sample_cnt + self.eps)  # [B]

        # sample_weight multiplies the per-sample loss
        w = sample_weight.clamp_min(0.0)
        weighted = per_sample_mean * w

        denom = w.sum().clamp_min(self.eps)
        return weighted.sum() / denom

# ----------------------------
# Train loop
# ----------------------------

def build_rows(jsonl_path: str) -> List[Row]:
    rows: List[Row] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            j = _loads(line)
            img = j.get("roi_image_path") or ""
            labels = j.get("labels") if isinstance(j.get("labels"), dict) else {}
            flat = flatten_labels(labels)
            w = float(j.get("sample_weight", 1.0) or 1.0)
            rows.append(Row(image_path=img, flat=flat, weight=w))
    return rows

def build_keyspace(rows: List[Row], min_freq: int = 5) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for r in rows:
        for k in r.flat.keys():
            freq[k] = freq.get(k, 0) + 1
    keys = [k for k, c in freq.items() if c >= min_freq]
    keys.sort()
    return {k: i for i, k in enumerate(keys)}

def split(rows: List[Row], val_frac: float = 0.15, seed: int = 1337) -> Tuple[List[Row], List[Row]]:
    rr = rows[:]
    random.Random(seed).shuffle(rr)
    n = len(rr)
    nv = int(n * val_frac)
    return rr[nv:], rr[:nv]

@torch.no_grad()
def evaluate(model, loader, loss_fn, device):
    model.eval()
    total = 0.0
    wsum = 0.0
    for x, y, m, w in loader:
        x = x.to(device)
        y = y.to(device)
        m = m.to(device)
        w = w.to(device)
        pred = model(x)
        loss = loss_fn(pred, y, m, w)
        # loss is already normalized by sum weights; estimate by multiplying back
        total += float(loss.item()) * float(w.sum().item())
        wsum += float(w.sum().item())
    if wsum <= 0:
        return None
    return total / wsum

def main():
    jsonl_path = os.environ.get("TRAIN_JSONL_PATH", "/mnt/data/train_dataset.jsonl")
    out_dir = os.environ.get("TRAIN_OUT_DIR", "/mnt/data/model_out")
    os.makedirs(out_dir, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    epochs = int(os.environ.get("TRAIN_EPOCHS", "5"))
    batch_size = int(os.environ.get("TRAIN_BATCH_SIZE", "32"))
    lr = float(os.environ.get("TRAIN_LR", "3e-4"))
    min_freq = int(os.environ.get("TRAIN_MIN_KEY_FREQ", "5"))
    img_size = int(os.environ.get("TRAIN_IMAGE_SIZE", "224"))
    seed = int(os.environ.get("TRAIN_SEED", "1337"))

    if not os.path.exists(jsonl_path):
        raise SystemExit(f"Missing dataset: {jsonl_path}")

    rows = build_rows(jsonl_path)
    if len(rows) < 100:
        raise SystemExit(f"Not enough rows to train (need ~100+). Have {len(rows)}")

    key_to_idx = build_keyspace(rows, min_freq=min_freq)
    if len(key_to_idx) < 1:
        raise SystemExit("No label keys met min frequency. Lower TRAIN_MIN_KEY_FREQ.")

    train_rows, val_rows = split(rows, val_frac=0.15, seed=seed)

    ds_tr = JsonlSkinDataset(train_rows, key_to_idx, image_size=img_size)
    ds_va = JsonlSkinDataset(val_rows, key_to_idx, image_size=img_size)

    dl_tr = DataLoader(ds_tr, batch_size=batch_size, shuffle=True, num_workers=2, pin_memory=torch.cuda.is_available())
    dl_va = DataLoader(ds_va, batch_size=batch_size, shuffle=False, num_workers=2, pin_memory=torch.cuda.is_available())

    model = MultiRegressor(out_dim=len(key_to_idx)).to(device)
    loss_fn = WeightedMaskedMSE()
    opt = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    best = None
    best_path = os.path.join(out_dir, "model.pt")

    for ep in range(1, epochs + 1):
        model.train()
        running = 0.0
        wsum = 0.0

        for x, y, m, w in dl_tr:
            x = x.to(device)
            y = y.to(device)
            m = m.to(device)
            w = w.to(device)

            pred = model(x)
            loss = loss_fn(pred, y, m, w)

            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

            running += float(loss.item()) * float(w.sum().item())
            wsum += float(w.sum().item())

        train_loss = (running / wsum) if wsum > 0 else None
        val_loss = evaluate(model, dl_va, loss_fn, device)

        print(f"epoch {ep}/{epochs} train={train_loss} val={val_loss}")

        if val_loss is not None and (best is None or val_loss < best):
            best = val_loss
            torch.save(model.state_dict(), best_path)

    # write manifest (label mapping)
    manifest = {
        "created_at": datetime_utc_iso(),
        "label_keys": list(key_to_idx.keys()),
        "key_to_index": key_to_idx,
        "image_size": img_size,
        "trainer": "train_pytorch.py",
        "best_val_loss": best,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Saved: {best_path}")
    print(f"Saved: {os.path.join(out_dir, 'manifest.json')}")

def datetime_utc_iso():
    import datetime
    return datetime.datetime.utcnow().isoformat()

if __name__ == "__main__":
    main()
