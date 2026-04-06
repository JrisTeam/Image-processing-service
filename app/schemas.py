from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Generic type variable for PaginatedResponse
# ---------------------------------------------------------------------------

T = TypeVar("T")


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class UserOut(BaseModel):
    id: UUID
    username: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    password: str


class RegisterResponse(BaseModel):
    user: UserOut
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: UserOut
    access_token: str
    token_type: str


# ---------------------------------------------------------------------------
# Transformation operation schemas (discriminated union)
# ---------------------------------------------------------------------------


class ResizeOp(BaseModel):
    type: Literal["resize"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class CropOp(BaseModel):
    type: Literal["crop"]
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class RotateOp(BaseModel):
    type: Literal["rotate"]
    angle: float


class FlipOp(BaseModel):
    type: Literal["flip"]


class MirrorOp(BaseModel):
    type: Literal["mirror"]


class CompressOp(BaseModel):
    type: Literal["compress"]
    quality: int = Field(ge=1, le=100)


class FormatOp(BaseModel):
    type: Literal["format"]
    target: Literal["JPEG", "PNG", "WEBP", "GIF", "BMP"]


class WatermarkOp(BaseModel):
    type: Literal["watermark"]
    overlay_url: str
    position: Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]


class FilterOp(BaseModel):
    type: Literal["filter"]
    filter_type: Literal["grayscale", "sepia"]


Operation = Annotated[
    ResizeOp | CropOp | RotateOp | FlipOp | MirrorOp | CompressOp | FormatOp | WatermarkOp | FilterOp,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Image schemas
# ---------------------------------------------------------------------------


class ImageRecordOut(BaseModel):
    id: UUID
    storage_url: str
    format: str
    width: int
    height: int
    size_bytes: int
    uploaded_at: datetime


class TransformationRecordOut(BaseModel):
    id: UUID
    source_image_id: UUID
    operations: list[Operation]
    storage_url: str
    created_at: datetime


class TransformRequest(BaseModel):
    operations: list[Operation]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    limit: int
    total_items: int
    total_pages: int
