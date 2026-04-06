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
        img = _apply_op(img, op)
    return img


def _apply_op(img: Image.Image, op: Operation) -> Image.Image:
    if isinstance(op, ResizeOp):
        return _apply_resize(img, op)
    if isinstance(op, CropOp):
        return _apply_crop(img, op)
    if isinstance(op, RotateOp):
        return img.rotate(op.angle, expand=True)
    if isinstance(op, FlipOp):
        return ImageOps.flip(img)
    if isinstance(op, MirrorOp):
        return ImageOps.mirror(img)
    if isinstance(op, CompressOp):
        return _apply_compress(img, op)
    if isinstance(op, FormatOp):
        return _apply_format(img, op)
    if isinstance(op, WatermarkOp):
        return _apply_watermark(img, op)
    if isinstance(op, FilterOp):
        return _apply_filter(img, op)
    return img


def _apply_resize(img: Image.Image, op: ResizeOp) -> Image.Image:
    return img.resize((op.width, op.height))


def _apply_crop(img: Image.Image, op: CropOp) -> Image.Image:
    if op.x + op.width > img.width or op.y + op.height > img.height:
        raise ValueError(
            f"Crop region ({op.x}, {op.y}, {op.width}x{op.height}) "
            f"exceeds image dimensions ({img.width}x{img.height})"
        )
    return img.crop((op.x, op.y, op.x + op.width, op.y + op.height))


def _apply_compress(img: Image.Image, op: CompressOp) -> Image.Image:
    # Quality is applied at save time; store it in image.info so callers can use it.
    img.info["quality"] = op.quality
    return img


def _apply_format(img: Image.Image, op: FormatOp) -> Image.Image:
    target = op.target
    if target == "JPEG" and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    img.format = target  # type: ignore[assignment]
    return img


def _apply_watermark(img: Image.Image, op: WatermarkOp) -> Image.Image:
    with urllib.request.urlopen(op.overlay_url) as resp:  # noqa: S310
        overlay_data = resp.read()
    overlay = Image.open(io.BytesIO(overlay_data)).convert("RGBA")
    base = img.convert("RGBA")
    pos_fn = _POSITION_OFFSETS[op.position]
    x, y = pos_fn(base.width, base.height, overlay.width, overlay.height)
    base.paste(overlay, (x, y), mask=overlay)
    return base


def _apply_filter(img: Image.Image, op: FilterOp) -> Image.Image:
    if op.filter_type == "grayscale":
        return ImageOps.grayscale(img).convert("RGB")
    if op.filter_type == "sepia":
        return img.convert("RGB").convert("RGB", _SEPIA_MATRIX)
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
