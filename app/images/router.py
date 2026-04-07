import io
import math
from typing import Annotated
from uuid import uuid4

import redis as redis_lib
from PIL import Image as PILImage
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.rate_limiter import check_rate_limit
from app.db.models import ImageRecord, TransformationRecord, User
from app.db.session import get_db
from app.schemas import (
    ImageRecordOut,
    PaginatedResponse,
    TransformationRecordOut,
    TransformRequest,
)
from app.storage import client as storage
from app.transforms.processor import apply_pipeline, pipeline_hash

# Module-level Redis client (lazy-initialised)
_redis_client = None

TRANSFORM_CACHE_TTL = 3600  # 1 hour


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(tags=["images"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_FORMATS = {"JPEG", "PNG", "GIF", "WEBP", "BMP", "TIFF"}
FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}


@router.post("/", response_model=ImageRecordOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
        file: UploadFile,
        user: CurrentUser,
        db: DbSession,
):
    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 20 MB limit",
        )

    try:
        img = PILImage.open(io.BytesIO(data))
        img.verify()
        img = PILImage.open(io.BytesIO(data))
        fmt = img.format
        if fmt not in ALLOWED_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported image format",
            )
        width, height = img.size
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image format",
        )

    image_id = str(uuid4())
    ext = fmt.lower()
    key = f"images/{user.id}/{image_id}.{ext}"
    content_type = FORMAT_CONTENT_TYPES.get(fmt, "application/octet-stream")
    storage_url = storage.upload(key, data, content_type)

    record = ImageRecord(
        id=image_id,
        owner_id=str(user.id),
        storage_key=key,
        storage_url=storage_url,
        format=fmt,
        width=width,
        height=height,
        size_bytes=len(data),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return ImageRecordOut(
        id=record.id,
        storage_url=record.storage_url,
        format=record.format,
        width=record.width,
        height=record.height,
        size_bytes=record.size_bytes,
        uploaded_at=record.uploaded_at,
    )


@router.get("/{image_id}", response_model=ImageRecordOut)
async def get_image(
        image_id: str,
        user: CurrentUser,
        db: DbSession,
):
    record = await db.scalar(
        select(ImageRecord).where(
            ImageRecord.id == image_id, ImageRecord.owner_id == str(user.id)
        )
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    return ImageRecordOut(
        id=record.id,
        storage_url=record.storage_url,
        format=record.format,
        width=record.width,
        height=record.height,
        size_bytes=record.size_bytes,
        uploaded_at=record.uploaded_at,
    )


@router.get("/", response_model=PaginatedResponse[ImageRecordOut])
async def list_images(
        user: CurrentUser,
        db: DbSession,
        page: Annotated[int, Query(ge=1)] = 1,
        limit: Annotated[int, Query(ge=1)] = 10,
):
    effective_limit = min(limit, 100)
    offset = (page - 1) * effective_limit

    total_items = await db.scalar(
        select(func.count())
        .select_from(ImageRecord)
        .where(ImageRecord.owner_id == str(user.id))
    )
    total_items = total_items or 0
    total_pages = math.ceil(total_items / effective_limit) if total_items > 0 else 1

    rows = await db.scalars(
        select(ImageRecord)
        .where(ImageRecord.owner_id == str(user.id))
        .order_by(ImageRecord.uploaded_at.desc())
        .offset(offset)
        .limit(effective_limit)
    )
    items = [
        ImageRecordOut(
            id=r.id,
            storage_url=r.storage_url,
            format=r.format,
            width=r.width,
            height=r.height,
            size_bytes=r.size_bytes,
            uploaded_at=r.uploaded_at,
        )
        for r in rows
    ]

    return PaginatedResponse(
        items=items,
        page=page,
        limit=effective_limit,
        total_items=total_items,
        total_pages=total_pages,
    )


def _check_rate_limit_safe(user_id) -> tuple[bool, int]:
    """Check rate limit, allowing through if Redis is unavailable."""
    try:
        redis = _get_redis()
        return check_rate_limit(user_id, redis)
    except Exception:
        return True, 0


def _get_cache_hit(p_hash: str):
    """Return cached value for a pipeline hash, or None if unavailable."""
    try:
        return _get_redis().get(f"transform:{p_hash}")
    except Exception:
        return None


def _set_cache(p_hash: str) -> None:
    """Cache a pipeline hash result; non-fatal if Redis is unavailable."""
    try:
        _get_redis().set(f"transform:{p_hash}", "1", ex=TRANSFORM_CACHE_TTL)
    except Exception:
        pass


def _fetch_image_bytes(storage_key: str) -> bytes:
    """Fetch raw image bytes from storage; raises HTTPException on failure."""
    try:
        s3 = storage._get_s3()
        obj = s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=storage_key)
        return obj["Body"].read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch source image",
        ) from exc


def _render_pipeline(
        image_bytes: bytes, operations, src_format: str
) -> tuple[bytes, str]:
    """Apply pipeline and encode result; returns (result_bytes, pil_format)."""
    from app.schemas import FormatOp as _FormatOp

    try:
        pil_image = PILImage.open(io.BytesIO(image_bytes))
        result_image = apply_pipeline(pil_image, operations)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    format_ops = [op for op in operations if isinstance(op, _FormatOp)]
    out_format = (
        format_ops[-1].target
        if format_ops
        else (result_image.format or pil_image.format or src_format or "PNG").upper()
    )
    pil_format = "JPEG" if out_format == "JPG" else out_format

    if pil_format == "JPEG" and result_image.mode in ("RGBA", "P", "LA"):
        result_image = result_image.convert("RGB")

    quality = result_image.info.get("quality", 85)
    out_buf = io.BytesIO()
    save_kwargs: dict = {"format": pil_format}
    if pil_format in ("JPEG", "WEBP"):
        save_kwargs["quality"] = quality
    result_image.save(out_buf, **save_kwargs)
    return out_buf.getvalue(), pil_format


@router.post("/{image_id}/transform", response_model=TransformationRecordOut)
async def transform_image(
        image_id: str,
        body: TransformRequest,
        response: Response,
        user: CurrentUser,
        db: DbSession,
):
    # --- Rate limiting ---
    allowed, retry_after = _check_rate_limit_safe(user.id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    # --- Ownership check ---
    image_record = await db.scalar(
        select(ImageRecord).where(
            ImageRecord.id == image_id,
            ImageRecord.owner_id == str(user.id),
        )
    )
    if not image_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    # --- Compute pipeline hash and check cache ---
    p_hash = pipeline_hash(image_record.id, body.operations)

    if _get_cache_hit(p_hash):
        existing = await db.scalar(
            select(TransformationRecord).where(
                TransformationRecord.pipeline_hash == p_hash,
                TransformationRecord.source_image_id == image_id,
            )
        )
        if existing:
            return TransformationRecordOut(
                id=existing.id,
                source_image_id=existing.source_image_id,
                operations=existing.operations,
                storage_url=existing.storage_url,
                created_at=existing.created_at,
            )

    # --- Cache miss: fetch, process, upload ---
    image_bytes = _fetch_image_bytes(image_record.storage_key)
    result_bytes, pil_format = _render_pipeline(
        image_bytes, body.operations, image_record.format
    )

    transform_key = storage.generate_transform_key(image_record.id, p_hash)
    content_type = FORMAT_CONTENT_TYPES.get(pil_format, "application/octet-stream")
    transform_url = storage.upload(transform_key, result_bytes, content_type)

    # --- Persist TransformationRecord ---
    ops_data = [op.model_dump(mode="json") for op in body.operations]
    transform_record = TransformationRecord(
        id=str(uuid4()),
        source_image_id=image_id,
        pipeline_hash=p_hash,
        operations=ops_data,
        storage_key=transform_key,
        storage_url=transform_url,
    )
    db.add(transform_record)
    await db.commit()
    await db.refresh(transform_record)

    _set_cache(p_hash)

    return TransformationRecordOut(
        id=transform_record.id,
        source_image_id=transform_record.source_image_id,
        operations=transform_record.operations,
        storage_url=transform_record.storage_url,
        created_at=transform_record.created_at,
    )
