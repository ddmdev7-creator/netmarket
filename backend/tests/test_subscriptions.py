"""Tests for vendor subscription plans, subscribing, and admin confirmation."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.subscriptions import service
from app.subscriptions.models import SubscriptionPlan, SubscriptionStatus, VendorSubscription
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers


async def test_list_plans_is_public(client: AsyncClient, subscription_plan: SubscriptionPlan) -> None:
    response = await client.get("/subscriptions/plans")

    assert response.status_code == 200
    names = [plan["name"] for plan in response.json()]
    assert "Premium mensuel" in names


async def test_vendor_can_subscribe(
    client: AsyncClient, vendor_user: User, subscription_plan: SubscriptionPlan
) -> None:
    response = await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["plan"]["id"] == str(subscription_plan.id)


async def test_subscribing_twice_while_pending_fails(
    client: AsyncClient, vendor_user: User, subscription_plan: SubscriptionPlan
) -> None:
    headers = auth_headers(vendor_user)
    await client.post("/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=headers)

    response = await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=headers
    )

    assert response.status_code == 409


async def test_get_my_subscription_returns_latest(
    client: AsyncClient, vendor_user: User, subscription_plan: SubscriptionPlan
) -> None:
    headers = auth_headers(vendor_user)
    await client.post("/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=headers)

    response = await client.get("/subscriptions/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


async def test_get_my_subscription_without_one_returns_null(client: AsyncClient, vendor_user: User) -> None:
    response = await client.get("/subscriptions/me", headers=auth_headers(vendor_user))

    assert response.status_code == 200
    assert response.json() is None


async def test_admin_can_confirm_pending_subscription(
    client: AsyncClient, vendor_user: User, admin_user: User, subscription_plan: SubscriptionPlan
) -> None:
    subscribe_response = await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user)
    )
    subscription_id = subscribe_response.json()["id"]

    response = await client.post(
        f"/admin/subscriptions/{subscription_id}/confirm", headers=auth_headers(admin_user)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["started_at"] is not None
    assert body["expires_at"] is not None


async def test_admin_cannot_confirm_twice(
    client: AsyncClient, vendor_user: User, admin_user: User, subscription_plan: SubscriptionPlan
) -> None:
    subscribe_response = await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user)
    )
    subscription_id = subscribe_response.json()["id"]
    admin_headers = auth_headers(admin_user)
    await client.post(f"/admin/subscriptions/{subscription_id}/confirm", headers=admin_headers)

    response = await client.post(f"/admin/subscriptions/{subscription_id}/confirm", headers=admin_headers)

    assert response.status_code == 409


async def test_admin_can_cancel_subscription(
    client: AsyncClient, vendor_user: User, admin_user: User, subscription_plan: SubscriptionPlan
) -> None:
    subscribe_response = await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user)
    )
    subscription_id = subscribe_response.json()["id"]

    response = await client.post(f"/admin/subscriptions/{subscription_id}/cancel", headers=auth_headers(admin_user))

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_non_admin_cannot_list_admin_subscriptions(client: AsyncClient, vendor_user: User) -> None:
    response = await client.get("/admin/subscriptions", headers=auth_headers(vendor_user))

    assert response.status_code == 403


async def test_admin_can_filter_pending_subscriptions(
    client: AsyncClient, vendor_user: User, admin_user: User, subscription_plan: SubscriptionPlan
) -> None:
    await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user)
    )

    response = await client.get("/admin/subscriptions?status=pending", headers=auth_headers(admin_user))

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_expired_subscription_is_not_premium(
    db_session: AsyncSession, vendor: Vendor, subscription_plan: SubscriptionPlan
) -> None:
    expired = VendorSubscription(
        vendor_id=vendor.id,
        plan_id=subscription_plan.id,
        status=SubscriptionStatus.ACTIVE,
        started_at=datetime.now(timezone.utc) - timedelta(days=40),
        expires_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(expired)
    await db_session.flush()

    assert await service.is_premium(db_session, vendor.id) is False
