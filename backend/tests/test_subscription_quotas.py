"""Quotas par formule, commission réduite, renouvellement enchaîné, essais
gratuits et tâche périodique (expiration, rappels, grâce)."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Product, ProductStatus
from app.notifications.models import Notification, NotificationType
from app.subscriptions import jobs, quotas
from app.subscriptions.models import SubscriptionPlan, SubscriptionSettings, SubscriptionStatus, VendorSubscription
from app.users.models import User
from app.vendors.models import Vendor, VendorStatus
from tests.conftest import auth_headers


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def free_plan(db_session: AsyncSession) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name="Gratuit",
        price_gnf=0,
        duration_days=0,
        is_free=True,
        max_products=2,
        max_images_per_product=2,
        ai_enhancements_per_month=1,
        commission_discount=0,
    )
    db_session.add(plan)
    await db_session.flush()
    return plan


async def _activate(
    db_session: AsyncSession, vendor: Vendor, plan: SubscriptionPlan, *, days_left: float = 20, trial: bool = False
) -> VendorSubscription:
    sub = VendorSubscription(
        vendor_id=vendor.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        is_trial=trial,
        started_at=_now() - timedelta(days=5),
        expires_at=_now() + timedelta(days=days_left),
    )
    db_session.add(sub)
    await db_session.flush()
    return sub


def _product_payload(category: Category, **extra) -> dict:
    return {"category_id": str(category.id), "name": "Article", "price": 1000, "stock": 1, **extra}


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 150), (10, 120, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def test_free_plan_limits_products_in_sale(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user: User,
    vendor: Vendor,
    category: Category,
    product: Product,
    free_plan: SubscriptionPlan,
    subscription_plan: SubscriptionPlan,
) -> None:
    headers = auth_headers(vendor_user)
    assert (await client.post("/products", json=_product_payload(category), headers=headers)).status_code == 201
    refused = await client.post("/products", json=_product_payload(category), headers=headers)
    assert refused.status_code == 403
    assert "2 produits" in refused.json()["detail"]

    # Remettre en vente un produit masqué compte aussi.
    product.status = ProductStatus.INACTIVE
    await db_session.flush()
    assert (await client.post("/products", json=_product_payload(category), headers=headers)).status_code == 201
    reactivate = await client.patch(f"/products/{product.id}", json={"status": "active"}, headers=headers)
    assert reactivate.status_code == 403

    await _activate(db_session, vendor, subscription_plan)
    assert (await client.patch(f"/products/{product.id}", json={"status": "active"}, headers=headers)).status_code == 200


async def test_images_per_product_follow_the_plan(
    client: AsyncClient, vendor_user: User, category: Category, free_plan: SubscriptionPlan
) -> None:
    headers = auth_headers(vendor_user)
    too_many = await client.post("/products", json=_product_payload(category, images=["a", "b", "c"]), headers=headers)
    assert too_many.status_code == 403
    assert "2 photos" in too_many.json()["detail"]
    assert (await client.post("/products", json=_product_payload(category, images=["a", "b"]), headers=headers)).status_code == 201


async def test_ai_enhancements_are_counted_per_month(
    client: AsyncClient, vendor_user: User, free_plan: SubscriptionPlan
) -> None:
    headers = auth_headers(vendor_user)
    files = [("files", ("p.jpg", _jpeg(), "image/jpeg"))]
    assert (await client.post("/uploads/images/enhance", files=files, headers=headers)).status_code == 200
    second = await client.post("/uploads/images/enhance", files=files, headers=headers)
    assert second.status_code == 403
    overview = (await client.get("/subscriptions/me/overview", headers=headers)).json()
    assert overview["ai_enhancements"] == {"used": 1, "limit": 1}
    assert overview["plan"]["name"] == "Gratuit"


async def test_plan_lowers_the_commission(
    db_session: AsyncSession, vendor: Vendor, subscription_plan: SubscriptionPlan, free_plan: SubscriptionPlan
) -> None:
    vendor.commission_rate = 10
    await db_session.flush()
    assert float(await quotas.effective_commission_rate(db_session, vendor)) == 10
    await _activate(db_session, vendor, subscription_plan)
    assert float(await quotas.effective_commission_rate(db_session, vendor)) == 8


async def test_renewal_is_stacked_after_the_current_period(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user: User,
    admin_user: User,
    vendor: Vendor,
    subscription_plan: SubscriptionPlan,
) -> None:
    current = await _activate(db_session, vendor, subscription_plan, days_left=10)
    renewal = await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user)
    )
    assert renewal.status_code == 200
    confirmed = await client.post(
        f"/admin/subscriptions/{renewal.json()['id']}/confirm", headers=auth_headers(admin_user)
    )
    assert confirmed.status_code == 200, confirmed.text
    started = datetime.fromisoformat(confirmed.json()["started_at"])
    assert abs((started - current.expires_at).total_seconds()) < 1

    overview = (await client.get("/subscriptions/me/overview", headers=auth_headers(vendor_user))).json()
    assert overview["current"]["id"] == str(current.id)
    assert overview["scheduled"]["id"] == renewal.json()["id"]


async def test_paid_subscription_cannot_be_cancelled_by_the_vendor(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user: User,
    vendor: Vendor,
    subscription_plan: SubscriptionPlan,
) -> None:
    headers = auth_headers(vendor_user)
    active = await _activate(db_session, vendor, subscription_plan)
    assert (await client.post(f"/subscriptions/{active.id}/cancel", headers=headers)).status_code == 403

    pending = await client.post("/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=headers)
    withdrawn = await client.post(f"/subscriptions/{pending.json()['id']}/cancel", headers=headers)
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "cancelled"


async def test_trial_once_per_plan_and_payment_ends_it(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user: User,
    admin_user: User,
    vendor: Vendor,
    subscription_plan: SubscriptionPlan,
) -> None:
    admin = auth_headers(admin_user)
    body = {"vendor_id": str(vendor.id), "plan_id": str(subscription_plan.id), "days": 14}
    trial = await client.post("/admin/subscriptions/trials", json=body, headers=admin)
    assert trial.status_code == 201, trial.text
    assert trial.json()["is_trial"] is True
    # Pendant l'essai : un 2e essai n'a pas de sens.
    assert (await client.post("/admin/subscriptions/trials", json=body, headers=admin)).status_code == 409

    pending = await client.post(
        "/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user)
    )
    confirmed = await client.post(f"/admin/subscriptions/{pending.json()['id']}/confirm", headers=admin)
    # Le paiement remplace l'essai tout de suite, sans attendre sa fin.
    started = datetime.fromisoformat(confirmed.json()["started_at"])
    assert started <= _now()
    overview = (await client.get("/subscriptions/me/overview", headers=auth_headers(vendor_user))).json()
    assert overview["current"]["is_trial"] is False
    assert overview["trial_used_plan_ids"] == [str(subscription_plan.id)]

    # Essai déjà utilisé pour cette formule, même une fois l'abonnement terminé.
    await db_session.execute(
        VendorSubscription.__table__.update().values(status=SubscriptionStatus.EXPIRED, expires_at=_now())
    )
    again = await client.post("/admin/subscriptions/trials", json=body, headers=admin)
    assert again.status_code == 409
    assert "déjà profité" in again.json()["detail"]


async def test_auto_trial_on_shop_approval(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    vendor: Vendor,
    subscription_plan: SubscriptionPlan,
) -> None:
    db_session.add(SubscriptionSettings(auto_trial_enabled=True, auto_trial_plan_id=subscription_plan.id, auto_trial_days=10))
    vendor.status = VendorStatus.PENDING
    await db_session.flush()

    response = await client.patch(f"/admin/vendors/{vendor.id}", json={"status": "approved"}, headers=auth_headers(admin_user))
    assert response.status_code == 200, response.text
    current = await quotas.current_subscription(db_session, vendor.id)
    assert current is not None and current.is_trial
    assert 9 <= (current.expires_at - _now()).days <= 10


async def _notification_count(db_session: AsyncSession, user: User) -> int:
    return (
        await db_session.execute(select(func.count()).select_from(Notification).where(Notification.user_id == user.id))
    ).scalar_one()


async def test_job_expires_then_hides_excess_products_after_grace(
    db_session: AsyncSession,
    vendor_user: User,
    vendor: Vendor,
    category: Category,
    subscription_plan: SubscriptionPlan,
    free_plan: SubscriptionPlan,
) -> None:
    for i in range(4):
        db_session.add(Product(vendor_id=vendor.id, category_id=category.id, name=f"P{i}", price=1000, stock=1))
    sub = await _activate(db_session, vendor, subscription_plan, days_left=-2)

    await jobs.run_once(db_session)
    await db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.EXPIRED
    # Encore en période de grâce : rien n'est masqué.
    assert await quotas.count_active_products(db_session, vendor.id) == 4
    assert await _notification_count(db_session, vendor_user) == 1

    await jobs.run_once(db_session, now=_now() + timedelta(days=6))
    assert await quotas.count_active_products(db_session, vendor.id) == 2
    assert await _notification_count(db_session, vendor_user) == 2
    # Passage suivant : déjà traité.
    await jobs.run_once(db_session, now=_now() + timedelta(days=7))
    assert await _notification_count(db_session, vendor_user) == 2


async def test_trial_reminders_are_sent_once_per_threshold(
    db_session: AsyncSession, vendor_user: User, vendor: Vendor, subscription_plan: SubscriptionPlan
) -> None:
    sub = await _activate(db_session, vendor, subscription_plan, days_left=2.5, trial=True)
    await jobs.run_once(db_session)
    assert sub.last_reminder_days == 3
    await jobs.run_once(db_session)
    assert await _notification_count(db_session, vendor_user) == 1
    await jobs.run_once(db_session, now=_now() + timedelta(days=2))
    assert sub.last_reminder_days == 1
    notes = (
        await db_session.execute(select(Notification.type).where(Notification.user_id == vendor_user.id))
    ).scalars().all()
    assert notes == [NotificationType.SUBSCRIPTION_REMINDER] * 2


async def test_admin_edits_plans_and_sees_vendor_overview(
    client: AsyncClient, admin_user: User, vendor: Vendor, subscription_plan: SubscriptionPlan, free_plan: SubscriptionPlan
) -> None:
    admin = auth_headers(admin_user)
    updated = await client.patch(
        f"/admin/subscription-plans/{free_plan.id}",
        json={"max_products": 20, "price_gnf": 5000, "ai_enhancements_per_month": None},
        headers=admin,
    )
    assert updated.status_code == 200
    # Gratuit : quotas modifiables, jamais de prix.
    assert updated.json()["max_products"] == 20 and updated.json()["price_gnf"] == 0
    assert updated.json()["ai_enhancements_per_month"] is None

    created = await client.post(
        "/admin/subscription-plans",
        json={"name": "Business", "price_gnf": 60000, "duration_days": 30, "max_products": None, "commission_discount": 4},
        headers=admin,
    )
    assert created.status_code == 201
    names = [p["name"] for p in (await client.get("/subscriptions/plans")).json()]
    assert names == ["Pro", "Business"]

    overview = (await client.get(f"/admin/subscriptions/vendors/{vendor.id}", headers=admin)).json()
    assert overview["products"]["limit"] == 20
    assert [p["name"] for p in overview["plans"]] == ["Gratuit", "Pro", "Business"]
