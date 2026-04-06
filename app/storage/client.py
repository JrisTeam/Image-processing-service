import boto3
from uuid import UUID

from app.core.config import settings

_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name=settings.R2_REGION,
        )
    return _s3


def upload(key: str, data: bytes, content_type: str) -> str:
    """Upload data to R2 and return the public URL."""
    _get_s3().put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"{settings.R2_PUBLIC_URL}/{key}"


def delete(key: str) -> None:
    """Delete an object from R2."""
    _get_s3().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)


def generate_key(image_id: UUID) -> str:
    """Return the storage key for an original image."""
    return f"images/{image_id}"


def generate_transform_key(source_id: UUID, pipeline_hash: str) -> str:
    """Return the storage key for a transformed image."""
    return f"transforms/{source_id}/{pipeline_hash}"
