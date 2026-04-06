import io
import math
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from PIL import Image as PILImage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import ImageRecord, User
from app.db.session import get_db
from app.schemas import ImageRecordOut, PaginatedResponse
from app.storage import client as storage

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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB limit")

    try:
        img = PILImage.open(io.BytesIO(data))
        img.verify()
        img = PILImage.open(io.BytesIO(data))
        fmt = img.format
        if fmt not in ALLOWED_FORMATS:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported image format")
        width, height = img.size
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported image format")

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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await db.scalar(
        select(ImageRecord).where(ImageRecord.id == image_id, ImageRecord.owner_id == str(user.id))
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

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
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    effective_limit = min(limit, 100)
    offset = (page - 1) * effective_limit

    total_items = await db.scalar(
        select(func.count()).select_from(ImageRecord).where(ImageRecord.owner_id == str(user.id))
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
