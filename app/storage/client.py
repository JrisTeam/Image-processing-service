from uuid import UUID

import boto3

from app.core.config import settings


def _make_client(service: str):
    return boto3.client(
        service,
        endpoint_url=settings.S3_ENDPOINT_URL,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
    )


_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = _make_client("s3")
    return _s3


def upload(key: str, data: bytes, content_type: str) -> str:
    """Upload data to S3-compatible storage and return the public URL."""
    _get_s3().put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"{settings.S3_PUBLIC_URL}/{key}"


def delete(key: str) -> None:
    """Delete an object from storage."""
    _get_s3().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)


def generate_key(image_id: UUID) -> str:
    return f"images/{image_id}"


def generate_transform_key(source_id: UUID, pipeline_hash: str) -> str:
    return f"transforms/{source_id}/{pipeline_hash}"
