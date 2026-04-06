"""
Integration tests for image CRUD endpoints.

Covers:
  - POST /images  (upload)
  - GET  /images/:id
  - GET  /images  (paginated listing)
  - Ownership isolation (cross-user 404)
  - 413 file-too-large
  - 415 unsupported format
  - Unauthenticated access → 401
"""
import io
import math
from unittest.mock import patch

import pytest
from PIL import Image as PILImage
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png(width: int = 64, height: int = 64) -> bytes:
    """Return raw bytes of a minimal in-memory PNG."""
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg(width: int = 32, height: int = 32) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), color=(0, 255, 0)).save(buf, format="JPEG")
    return buf.getvalue()


async def _register_and_token(client: AsyncClient, username: str,
                              password: str = "pass1234") -> str:  # NOSONAR — test helper, not a real credential
    resp = await client.post("/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload_file(data: bytes, filename: str = "test.png", content_type: str = "image/png"):
    return {"file": (filename, data, content_type)}


# ---------------------------------------------------------------------------
# POST /images — upload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_png_success(client: AsyncClient):
    token = await _register_and_token(client, "uploader1")
    with patch("app.storage.client.upload", return_value="https://cdn.example.com/images/x/y.png"):
        resp = await client.post(
            "/images/",
            headers=_auth(token),
            files=_upload_file(_make_png(), "photo.png", "image/png"),
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["format"] == "PNG"
    assert data["width"] == 64
    assert data["height"] == 64
    assert data["size_bytes"] > 0
    assert "id" in data
    assert "uploaded_at" in data


@pytest.mark.asyncio
async def test_upload_jpeg_success(client: AsyncClient):
    token = await _register_and_token(client, "uploader2")
    with patch("app.storage.client.upload", return_value="https://cdn.example.com/images/x/y.jpg"):
        resp = await client.post(
            "/images/",
            headers=_auth(token),
            files=_upload_file(_make_jpeg(), "photo.jpg", "image/jpeg"),
        )
    assert resp.status_code == 201
    assert resp.json()["format"] == "JPEG"


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/images/",
        files=_upload_file(_make_png()),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_unsupported_format_returns_415(client: AsyncClient):
    token = await _register_and_token(client, "uploader3")
    resp = await client.post(
        "/images/",
        headers=_auth(token),
        files=_upload_file(b"not an image at all", "file.txt", "text/plain"),
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_file_too_large_returns_413(client: AsyncClient):
    token = await _register_and_token(client, "uploader4")
    big_data = b"x" * (20 * 1024 * 1024 + 1)  # 20 MB + 1 byte
    resp = await client.post(
        "/images/",
        headers=_auth(token),
        files=_upload_file(big_data, "big.png", "image/png"),
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# GET /images/:id — retrieve single image
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_image_success(client: AsyncClient):
    token = await _register_and_token(client, "getter1")
    with patch("app.storage.client.upload", return_value="https://cdn.example.com/img.png"):
        upload_resp = await client.post(
            "/images/",
            headers=_auth(token),
            files=_upload_file(_make_png()),
        )
    image_id = upload_resp.json()["id"]

    resp = await client.get(f"/images/{image_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == image_id


@pytest.mark.asyncio
async def test_get_image_not_found_returns_404(client: AsyncClient):
    token = await _register_and_token(client, "getter2")
    resp = await client.get("/images/00000000-0000-0000-0000-000000000000", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_image_requires_auth(client: AsyncClient):
    resp = await client.get("/images/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Ownership isolation — cross-user access returns 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_image_cross_user_returns_404(client: AsyncClient):
    token_a = await _register_and_token(client, "owner_a")
    token_b = await _register_and_token(client, "owner_b")

    with patch("app.storage.client.upload", return_value="https://cdn.example.com/img.png"):
        upload_resp = await client.post(
            "/images/",
            headers=_auth(token_a),
            files=_upload_file(_make_png()),
        )
    image_id = upload_resp.json()["id"]

    # User B tries to access User A's image
    resp = await client.get(f"/images/{image_id}", headers=_auth(token_b))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /images — paginated listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_images_empty(client: AsyncClient):
    token = await _register_and_token(client, "lister1")
    resp = await client.get("/images/", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total_items"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_images_returns_own_images_only(client: AsyncClient):
    token_a = await _register_and_token(client, "lister2a")
    token_b = await _register_and_token(client, "lister2b")

    with patch("app.storage.client.upload", return_value="https://cdn.example.com/img.png"):
        for _ in range(3):
            await client.post("/images/", headers=_auth(token_a), files=_upload_file(_make_png()))
        for _ in range(2):
            await client.post("/images/", headers=_auth(token_b), files=_upload_file(_make_png()))

    resp_a = await client.get("/images/", headers=_auth(token_a))
    resp_b = await client.get("/images/", headers=_auth(token_b))

    assert resp_a.json()["total_items"] == 3
    assert resp_b.json()["total_items"] == 2


@pytest.mark.asyncio
async def test_list_images_pagination_math(client: AsyncClient):
    token = await _register_and_token(client, "lister3")
    n = 7

    with patch("app.storage.client.upload", return_value="https://cdn.example.com/img.png"):
        for _ in range(n):
            await client.post("/images/", headers=_auth(token), files=_upload_file(_make_png()))

    resp = await client.get("/images/?page=1&limit=3", headers=_auth(token))
    data = resp.json()
    assert data["total_items"] == n
    assert data["total_pages"] == math.ceil(n / 3)
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_images_ordered_by_upload_desc(client: AsyncClient):
    token = await _register_and_token(client, "lister4")

    with patch("app.storage.client.upload", return_value="https://cdn.example.com/img.png"):
        for _ in range(3):
            await client.post("/images/", headers=_auth(token), files=_upload_file(_make_png()))

    resp = await client.get("/images/", headers=_auth(token))
    items = resp.json()["items"]
    timestamps = [i["uploaded_at"] for i in items]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_list_images_limit_capped_at_100(client: AsyncClient):
    token = await _register_and_token(client, "lister5")
    resp = await client.get("/images/?limit=999", headers=_auth(token))
    assert resp.json()["limit"] == 100


@pytest.mark.asyncio
async def test_list_images_requires_auth(client: AsyncClient):
    resp = await client.get("/images/")
    assert resp.status_code == 401
