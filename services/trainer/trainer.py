# services/trainer/trainer.py

"""
Offline trainer scaffold (ROI-only donation dataset).

This version does NOT train a model yet — it builds a dataset index + basic stats
from donation storage to prove the data pipeline works, and prepares a manifest
you can use for versioned releases.

Next step after this: add labeling + training + bias checks + model export.
"""

import os
import json
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ModelManifest:
    version: str
    trained_at: str
    donation_count: int
    notes: str

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    donation_dir = Path(os.getenv("DONATION_STORE_DIR", "/data/donations"))
    out_dir = Path(os.getenv("OUT_DIR", "./out"))
    version = os.getenv("NEXT_MODEL_VERSION", f"0.2.{int(time.time())}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect all ROI jpgs under sharded folders
    files = sorted(donation_dir.rglob("*.jpg")) if donation_dir.exists() else []
    index = []

    for p in files:
        # filename is expected roi_sha256.jpg
        roi_sha = p.stem
        # sanity-check hash format (64 hex)
        if len(roi_sha) != 64:
            # fallback: compute it (keeps pipeline robust)
            roi_sha = sha256_file(p)

        index.append({
            "roi_sha256": roi_sha,
            "path": str(p),
        })

    # Write dataset index
    with open(out_dir / "dataset_index.json", "w") as f:
        json.dump({"count": len(index), "items": index}, f, indent=2)

    manifest = ModelManifest(
        version=version,
        trained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        donation_count=len(index),
        notes="Dataset index built from ROI-only donations. Add labeling + training + bias checks next."
    )

    with open(out_dir / "manifest.json", "w") as f:
        json.dump(manifest.__dict__, f, indent=2)

    print(f"Donation dataset: {len(index)} ROI images")
    print(f"Wrote: {out_dir / 'dataset_index.json'}")
    print(f"Wrote: {out_dir / 'manifest.json'}")
    print("Next: integrate labels + training, evaluate across subgroups, export model.pt (TorchScript), rollout with version pinning.")

if __name__ == "__main__":
    main()
