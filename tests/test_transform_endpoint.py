"""
Integration tests for POST /images/:id/transform endpoint.

Covers:
  - Successful transformation (resize)
  - Cache hit returns same record (identical id + storage_url)
  - 404 when image not owned by user
  - 422 when apply_pipeline raises ValueError (out-of-bounds crop)
  - 429 when rate limit exceeded (Retry-After header present)
  - 401 when unauthenticated
"""
import io
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image as PILImage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png(width: int = 64, height: int = 64) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), color=(100, 150, 200)).save(buf, format="PNG")
    return buf.getvalue()


async def _register_and_token(client: AsyncClient, username: str, password: str = "pass1234") -> str:
    resp = await client.post("/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _upload_image(client: AsyncClient, token: str, png_bytes: bytes | None = None) -> str:
    """Upload an image and return its id."""
    data = png_bytes or _make_png()
    with patch("app.storage.client.upload", return_value="https://cdn.example.com/img.png"):
        resp = await client.post(
            "/images/",
            headers=_auth(token),
            files={"file": ("test.png", data, "image/png")},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _mock_redis(allowed: bool = True, retry_after: int = 0):
    """Return a mock Redis client that always allows (or denies) requests."""
    mock = MagicMock()
    mock.zremrangebyscore.return_value = None
    mock.zcard.return_value = 0 if allowed else 100
    mock.zadd.return_value = None
    mock.expire.return_value = None
    mock.zrange.return_value = [(b"1234567890.0", 1234567890.0)]
    mock.get.return_value = None   # no cache hit by default
    mock.set.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Successful transformation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transform_resize_success(client: AsyncClient):
    token = await _register_and_token(client, "transform_user1")
    image_id = await _upload_image(client, token)

    png_bytes = _make_png(64, 64)

    mock_redis = _mock_redis(allowed=True)
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: png_bytes)}

    with (
        patch("app.images.router._get_redis", return_value=mock_redis),
        patch("app.storage.client._get_s3", return_value=mock_s3),
        patch("app.storage.client.upload", return_value="https://cdn.example.com/transforms/x/y.png"),
    ):
        resp = await client.post(
            f"/images/{image_id}/transform",
            headers=_auth(token),
            json={"operations": [{"type": "resize", "width": 32, "height": 32}]},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source_image_id"] == image_id
    assert "id" in data
    assert "storage_url" in data
    assert "created_at" in data
    assert data["operations"] == [{"type": "resize", "width": 32, "height": 32}]


# ---------------------------------------------------------------------------
# Cache hit returns same record
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transform_cache_hit_returns_same_record(client: AsyncClient):
    token = await _register_and_token(client, "transform_user2")
    image_id = await _upload_image(client, token)

    png_bytes = _make_png(64, 64)
    operations = [{"type": "resize", "width": 16, "height": 16}]

    mock_redis_no_cache = _mock_redis(allowed=True)
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: png_bytes)}

    # First call — cache miss, creates record
    with (
        patch("app.images.router._get_redis", return_value=mock_redis_no_cache),
        patch("app.storage.client._get_s3", return_value=mock_s3),
        patch("app.storage.client.upload", return_value="https://cdn.example.com/transforms/x/y.png"),
    ):
        resp1 = await client.post(
            f"/images/{image_id}/transform",
            headers=_auth(token),
            json={"operations": operations},
        )
    assert resp1.status_code == 200, resp1.text
    first_id = resp1.json()["id"]
    first_url = resp1.json()["storage_url"]

    # Second call — simulate cache hit
    mock_redis_with_cache = _mock_redis(allowed=True)
    mock_redis_with_cache.get.return_value = "1"  # cache hit

    with (
        patch("app.images.router._get_redis", return_value=mock_redis_with_cache),
    ):
        resp2 = await client.post(
            f"/images/{image_id}/transform",
            headers=_auth(token),
            json={"operations": operations},
        )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["id"] == first_id
    assert resp2.json()["storage_url"] == first_url


# ---------------------------------------------------------------------------
# 404 — image not owned by user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transform_cross_user_returns_404(client: AsyncClient):
    token_a = await _register_and_token(client, "transform_owner_a")
    token_b = await _register_and_token(client, "transform_owner_b")
    image_id = await _upload_image(client, token_a)

    mock_redis = _mock_redis(allowed=True)
    with patch("app.images.router._get_redis", return_value=mock_redis):
        resp = await client.post(
            f"/images/{image_id}/transform",
            headers=_auth(token_b),
            json={"operations": [{"type": "flip"}]},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 422 — out-of-bounds crop raises ValueError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transform_invalid_crop_returns_422(client: AsyncClient):
    token = await _register_and_token(client, "transform_user3")
    image_id = await _upload_image(client, token)

    png_bytes = _make_png(64, 64)
    mock_redis = _mock_redis(allowed=True)
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: png_bytes)}

    with (
        patch("app.images.router._get_redis", return_value=mock_redis),
        patch("app.storage.client._get_s3", return_value=mock_s3),
    ):
        resp = await client.post(
            f"/images/{image_id}/transform",
            headers=_auth(token),
            # crop region exceeds 64x64 image
            json={"operations": [{"type": "crop", "x": 0, "y": 0, "width": 200, "height": 200}]},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 429 — rate limit exceeded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transform_rate_limit_returns_429(client: AsyncClient):
    token = await _register_and_token(client, "transform_user4")
    image_id = await _upload_image(client, token)

    mock_redis = _mock_redis(allowed=False, retry_after=30)
    # Override zcard to return 100 (limit reached) and zrange for retry_after calc
    mock_redis.zcard.return_value = 100
    mock_redis.zrange.return_value = [("ts", 1234567890.0)]

    with patch("app.images.router._get_redis", return_value=mock_redis):
        resp = await client.post(
            f"/images/{image_id}/transform",
            headers=_auth(token),
            json={"operations": [{"type": "flip"}]},
        )
    assert resp.status_code == 429
    assert "retry-after" in resp.headers


# ---------------------------------------------------------------------------
# 401 — unauthenticated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transform_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/images/00000000-0000-0000-0000-000000000000/transform",
        json={"operations": [{"type": "flip"}]},
    )
    assert resp.status_code == 401
