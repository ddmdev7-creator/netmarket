"""Tests for the product image upload endpoint — exercises the real MinIO
service (docker-compose), not a mock, to prove the whole pipeline works."""

import io
import re
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.subscriptions.models import SubscriptionPlan, SubscriptionStatus, VendorSubscription
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers

_KEY_PATTERN = re.compile(r"^[0-9a-f-]{36}\.jpg$")


def _fake_jpeg(color: tuple[int, int, int] = (200, 120, 50)) -> bytes:
    image = Image.new("RGB", (400, 300), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


async def _make_premium(db_session: AsyncSession, vendor: Vendor, plan: SubscriptionPlan) -> None:
    db_session.add(
        VendorSubscription(
            vendor_id=vendor.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    await db_session.flush()


async def test_vendor_can_upload_images(client: AsyncClient, vendor_user: User) -> None:
    response = await client.post(
        "/uploads/images",
        files=[("files", ("produit.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 200
    keys = response.json()["keys"]
    assert len(keys) == 1
    assert _KEY_PATTERN.match(keys[0])


async def test_vendor_can_upload_multiple_images_at_once(client: AsyncClient, vendor_user: User) -> None:
    response = await client.post(
        "/uploads/images",
        files=[
            ("files", ("a.jpg", _fake_jpeg((10, 10, 10)), "image/jpeg")),
            ("files", ("b.jpg", _fake_jpeg((250, 250, 250)), "image/jpeg")),
        ],
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 200
    assert len(response.json()["keys"]) == 2


async def test_buyer_cannot_upload_images(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/uploads/images",
        files=[("files", ("produit.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 403


async def test_rejects_unsupported_content_type(client: AsyncClient, vendor_user: User) -> None:
    response = await client.post(
        "/uploads/images",
        files=[("files", ("doc.pdf", b"%PDF-1.4 fake", "application/pdf"))],
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 409


async def test_rejects_corrupted_image_content(client: AsyncClient, vendor_user: User) -> None:
    response = await client.post(
        "/uploads/images",
        files=[("files", ("fake.jpg", b"this is not really a jpeg", "image/jpeg"))],
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 409


async def test_uploaded_image_is_publicly_fetchable(client: AsyncClient, vendor_user: User) -> None:
    upload_response = await client.post(
        "/uploads/images",
        files=[("files", ("produit.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(vendor_user),
    )
    key = upload_response.json()["keys"][0]

    # No auth header — product images are public, same as GET /products/{id}.
    fetched = await client.get(f"/uploads/images/{key}")

    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/jpeg"


async def test_fetching_an_unknown_image_key_is_404(client: AsyncClient) -> None:
    response = await client.get("/uploads/images/00000000-0000-0000-0000-000000000000.jpg")

    assert response.status_code == 404


async def test_fetching_a_malformed_image_key_is_404(client: AsyncClient) -> None:
    response = await client.get("/uploads/images/not-a-valid-key")

    assert response.status_code == 404


async def test_non_premium_vendor_cannot_enhance_images(client: AsyncClient, vendor_user: User) -> None:
    response = await client.post(
        "/uploads/images/enhance",
        files=[("files", ("produit.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 403


async def test_premium_vendor_can_enhance_images(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user: User,
    vendor: Vendor,
    subscription_plan: SubscriptionPlan,
) -> None:
    await _make_premium(db_session, vendor, subscription_plan)

    response = await client.post(
        "/uploads/images/enhance",
        files=[("files", ("produit.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 200
    keys = response.json()["keys"]
    assert len(keys) == 1
    assert _KEY_PATTERN.match(keys[0])
