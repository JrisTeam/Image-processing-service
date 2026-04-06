from __future__ import annotations

import hashlib
import io
import json
import urllib.request
from typing import TYPE_CHECKING
from uuid import UUID

from PIL import Image, ImageOps

from app.schemas import (
    CompressOp,
    CropOp,
    FilterOp,
    FlipOp,
    FormatOp,
    MirrorOp,
    Operation,
    ResizeOp,
    RotateOp,
    WatermarkOp,
)

# ---------------------------------------------------------------------------
# Sepia transformation matrix
# ---------------------------------------------------------------------------

_SEPIA_MATRIX = [
    0.393, 0.769, 0.189, 0,
    0.349, 0.686, 0.168, 0,
    0.272, 0.534, 0.131, 0,
]

# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

_POSITION_OFFSETS = {
    "top-left": lambda iw, ih, ow, oh: (0, 0),
    "top-right": lambda iw, ih, ow, oh: (iw - ow, 0),
    "bottom-left": lambda iw, ih, ow, oh: (0, ih - oh),
    "bottom-right": lambda iw, ih, ow, oh: (iw - ow, ih - oh),
    "center": lambda iw, ih, ow, oh: ((iw - ow) // 2, (ih - oh) // 2),
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def apply_pipeline(image: Image.Image, pipeline: list[Operation]) -> Image.Image:
    """Apply a sequence of operations to a PIL image and return the result."""
    img = image.copy()

    for op in pipeline:
        if isinstance(op, ResizeOp):
            img = img.resize((op.width, op.height))

        elif isinstance(op, CropOp):
            if op.x + op.width > img.width or op.y + op.height > img.height:
                raise ValueError(
                    f"Crop region ({op.x}, {op.y}, {op.width}x{op.height}) "
                    f"exceeds image dimensions ({img.width}x{img.height})"
                )
            img = img.crop((op.x, op.y, op.x + op.width, op.y + op.height))

        elif isinstance(op, RotateOp):
            img = img.rotate(op.angle, expand=True)

        elif isinstance(op, FlipOp):
            img = ImageOps.flip(img)

        elif isinstance(op, MirrorOp):
            img = ImageOps.mirror(img)

        elif isinstance(op, CompressOp):
            # Quality is applied at save time; store it in image.info so callers can use it.
            img.info["quality"] = op.quality

        elif isinstance(op, FormatOp):
            target = op.target
            # JPEG does not support alpha or palette modes — convert as needed.
            if target == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.format = target  # type: ignore[assignment]

        elif isinstance(op, WatermarkOp):
            with urllib.request.urlopen(op.overlay_url) as resp:  # noqa: S310
                overlay_data = resp.read()
            overlay = Image.open(io.BytesIO(overlay_data)).convert("RGBA")

            # Ensure base image supports alpha compositing.
            base = img.convert("RGBA")
            pos_fn = _POSITION_OFFSETS[op.position]
            x, y = pos_fn(base.width, base.height, overlay.width, overlay.height)
            base.paste(overlay, (x, y), mask=overlay)
            img = base

        elif isinstance(op, FilterOp):
            if op.filter_type == "grayscale":
                img = ImageOps.grayscale(img).convert("RGB")
            elif op.filter_type == "sepia":
                rgb = img.convert("RGB")
                img = rgb.convert("RGB", _SEPIA_MATRIX)

    return img


def pipeline_hash(source_id: UUID, pipeline: list[Operation]) -> str:
    """Return the SHA-256 hex digest of the canonical JSON representation of the pipeline."""
    ops_data = [op.model_dump(mode="json") for op in pipeline]
    canonical = json.dumps(
        {"source_id": str(source_id), "pipeline": ops_data},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
