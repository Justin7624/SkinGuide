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

@dataclass
class Manifest:
    version: str
    trained_at: str
    labeled_samples: int
    val_samples: int
    metrics: Dict[str, float]
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
        logits = self.head(x)
        return logits

def load_image(path: Path, size=128) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Bad image: {path}")
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    return img

def load_label(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_dataset(donation_dir: Path, label_dir: Path) -> List[Tuple[Path, np.ndarray, np.ndarray]]:
    """
    Returns list of (img_path, y, mask) where:
      y: float32 [K] target values (0..1)
      mask: float32 [K] 1 if present, 0 if missing (sparse labels)
    """
    items = []
    imgs = sorted(donation_dir.rglob("*.jpg")) if donation_dir.exists() else []
    for img_path in imgs:
        roi_sha = img_path.stem
        lab_path = label_dir / f"{roi_sha}.json"
        if not lab_path.exists():
            continue

        lab = load_label(lab_path)
        labels = lab.get("labels", {}) or {}

        y = np.zeros((K,), dtype=np.float32)
        m = np.zeros((K,), dtype=np.float32)

        for i, key in enumerate(ATTRIBUTE_KEYS):
            if key in labels:
                v = float(labels[key])
                v = max(0.0, min(1.0, v))
                y[i] = v
                m[i] = 1.0

        # require at least one labeled attribute
        if float(m.sum()) < 1.0:
            continue

        items.append((img_path, y, m))
    return items

def masked_mse(pred, target, mask, eps=1e-6):
    diff = (pred - target) ** 2
    diff = diff * mask
    denom = mask.sum(dim=1).clamp_min(eps)
    per_ex = diff.sum(dim=1) / denom
    return per_ex.mean()

def main():
    donation_dir = Path(os.getenv("DONATION_STORE_DIR", "/data/donations"))
    label_dir = Path(os.getenv("DONATION_LABEL_DIR", "/data/donations/labels"))
    out_dir = Path(os.getenv("OUT_DIR", "./out"))
    version = os.getenv("NEXT_MODEL_VERSION", f"0.3.{int(time.time())}")

    out_dir.mkdir(parents=True, exist_ok=True)

    data = build_dataset(donation_dir, label_dir)
    if len(data) < 20:
        print(f"Not enough labeled samples to train (need ~20+, have {len(data)}).")
        print("Collect more labeled donations, then re-run.")
        return

    # Shuffle + split
    rng = np.random.default_rng(123)
    idx = np.arange(len(data))
    rng.shuffle(idx)
    split = int(0.8 * len(data))
    train_idx = idx[:split]
    val_idx = idx[split:]

    def make_batch(indices):
        xs, ys, ms = [], [], []
        for j in indices:
            img_path, y, m = data[int(j)]
            x = load_image(img_path, size=128)
            xs.append(x)
            ys.append(y)
            ms.append(m)
        X = torch.from_numpy(np.stack(xs)).permute(0, 3, 1, 2)  # NCHW
        Y = torch.from_numpy(np.stack(ys))
        M = torch.from_numpy(np.stack(ms))
        return X, Y, M

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TinySkinNet(out_dim=K).to(device)

    opt = optim.Adam(model.parameters(), lr=3e-4)
    epochs = int(os.getenv("EPOCHS", "8"))
    batch_size = int(os.getenv("BATCH_SIZE", "16"))

    # Create mini-batches
    train_list = train_idx.tolist()
    val_list = val_idx.tolist()

    def iter_batches(lst):
        for i in range(0, len(lst), batch_size):
            yield lst[i:i + batch_size]

    best_val = 1e9
    best_state = None

    for ep in range(1, epochs + 1):
        model.train()
        train_losses = []

        for b in iter_batches(train_list):
            X, Y, M = make_batch(b)
            X, Y, M = X.to(device), Y.to(device), M.to(device)

            logits = model(X)
            pred = torch.sigmoid(logits)

            loss = masked_mse(pred, Y, M)
            opt.zero_grad()
            loss.backward()
            opt.step()

            train_losses.append(float(loss.detach().cpu().item()))

        model.eval()
        with torch.no_grad():
            val_losses = []
            for b in iter_batches(val_list):
                X, Y, M = make_batch(b)
                X, Y, M = X.to(device), Y.to(device), M.to(device)
                pred = torch.sigmoid(model(X))
                loss = masked_mse(pred, Y, M)
                val_losses.append(float(loss.detach().cpu().item()))
            val_loss = float(np.mean(val_losses)) if val_losses else 1e9

        tr = float(np.mean(train_losses)) if train_losses else 1e9
        print(f"Epoch {ep}/{epochs} train={tr:.4f} val={val_loss:.4f}")

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    # Export TorchScript
    model.eval()
    example = torch.zeros((1, 3, 128, 128), dtype=torch.float32).to(device)
    traced = torch.jit.trace(model, example)
    out_model = out_dir / "model.pt"
    traced.save(str(out_model))

    # Write manifest
    manifest = Manifest(
        version=version,
        trained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        labeled_samples=len(train_list),
        val_samples=len(val_list),
        metrics={"val_masked_mse": best_val},
        notes="TinySkinNet baseline trained on ROI-only donations with sparse 0..1 labels. Add bias slices + calibration next.",
    )
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest.__dict__, f, indent=2)

    print(f"Saved: {out_model}")
    print(f"Saved: {out_dir / 'manifest.json'}")

if __name__ == "__main__":
    main()
