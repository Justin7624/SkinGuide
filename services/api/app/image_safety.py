# services/api/app/image_safety.py

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal, Optional, Tuple

from PIL import Image, ImageOps

from .config import settings

ImageType = Literal["jpeg", "png"]

@dataclass
class SanitizedImage:
    jpeg_bytes: bytes
    width: int
    height: int
    downscaled: bool
    source_type: ImageType

def sniff_type(data: bytes) -> Optional[ImageType]:
    if len(data) < 12:
        return None
    # JPEG: FF D8 FF
    if data[0:3] == b"\xFF\xD8\xFF":
        return "jpeg"
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if data[0:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None

def sanitize_upload_image(data: bytes) -> SanitizedImage:
    """
    Security/robustness:
      - sniff magic bytes (ignore declared content-type)
      - Pillow decode + EXIF orientation fix (exif_transpose)
      - strip metadata by re-encoding
      - enforce min dims + max pixels
      - downscale to MAX_IMAGE_DIM if needed
      - output: baseline JPEG bytes (no EXIF)
    """
    src_type = sniff_type(data)
    if not src_type:
        raise ValueError("unsupported_image_type")

    # Decode safely (verify + reopen)
    try:
        bio = BytesIO(data)
        im = Image.open(bio)
        im.verify()
        bio2 = BytesIO(data)
        im = Image.open(bio2)
        im = ImageOps.exif_transpose(im)
    except Exception:
        raise ValueError("decode_failed")

    # Convert to RGB safely (drop alpha; no transparency leaks)
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")

    w, h = im.size
    if w < settings.MIN_IMAGE_DIM or h < settings.MIN_IMAGE_DIM:
        raise ValueError("image_too_small")

    pixels = int(w) * int(h)
    if pixels > int(settings.MAX_IMAGE_PIXELS):
        raise ValueError("too_many_pixels")

    downscaled = False
    max_dim = int(settings.MAX_IMAGE_DIM)
    if max(w, h) > max_dim:
        downscaled = True
        if w >= h:
            new_w = max_dim
            new_h = max(1, int(round(h * (max_dim / w))))
        else:
            new_h = max_dim
            new_w = max(1, int(round(w * (max_dim / h))))
        im = im.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
        w, h = im.size

    # Re-encode to JPEG (no EXIF)
    out = BytesIO()
    im.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
    jpeg_bytes = out.getvalue()

    return SanitizedImage(
        jpeg_bytes=jpeg_bytes,
        width=w,
        height=h,
        downscaled=downscaled,
        source_type=src_type,
    )
