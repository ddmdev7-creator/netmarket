"""Colis non retiré au point de retrait : rappels, retour au vendeur par un
livreur, remboursement de l'acheteur (articles − aller − retour)."""

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.couriers.models import Courier
from app.delivery.models import DeliveryFeeTier
from app.notifications.models import Notification, NotificationType
from app.orders import returns
from app.orders.models import OrderStatus, SubOrder, SubOrderStatusEvent
from app.pickup_points.models import PickupPoint
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers, scan_handoff
from tests.test_ndjouribank import _balance, _overview, _settings, _top_up
from tests.test_payments import _add_to_cart

KALOUM = (9.5092, -13.7122)
NEAR_KALOUM = (9.5150, -13.7100)


@pytest.fixture
async def paid_parcel_at_point(
    client: AsyncClient,
    db_session: AsyncSession,
    buyer_user: User,
    admin_user: User,
    vendor_user: User,
    vendor: Vendor,
    product: Product,
    courier: Courier,
    manager_user: User,
    pickup_point: PickupPoint,
    monkeypatch: pytest.MonkeyPatch,
) -> dict:
    """Commande payée avec NdjouriBank, livrée au point (colis en attente)."""
    await _settings(client, admin_user, pickup_point_fee_per_parcel=2000, pickup_return_percent=50)
    db_session.add(DeliveryFeeTier(max_km=3, fee=10000, transit_days=0))
    vendor.latitude, vendor.longitude = KALOUM
    pickup_point.latitude, pickup_point.longitude = NEAR_KALOUM
    await db_session.flush()

    await _top_up(client, buyer_user, monkeypatch, 1_000_000)
    await _add_to_cart(client, buyer_user, product)
    checkout = await client.post(
        "/orders/checkout",
        json={
            "delivery_address": pickup_point.name,
            "delivery_type": "pickup_point",
            "pickup_point_id": str(pickup_point.id),
            "payment_method": "wallet",
        },
        headers=auth_headers(buyer_user),
    )
    assert checkout.status_code == 201, checkout.text
    order = checkout.json()
    sub_order_id = order["sub_orders"][0]["id"]
    vendor_headers = auth_headers(vendor_user)
    await client.patch(f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers)
    for step in ("confirmed", "preparing", "shipped"):
        response = await client.patch(f"/orders/sub-orders/{sub_order_id}/status", json={"status": step}, headers=vendor_headers)
        assert response.status_code == 200, response.text
    arrival = await scan_handoff(client, manager_user, sub_order_id)
    assert arrival.json()["status"] == "arrived_at_pickup_point"
    return {"order": order, "sub_order_id": sub_order_id}


async def _age(db_session: AsyncSession, sub_order_id: str, days: float) -> SubOrder:
    await db_session.execute(
        update(SubOrderStatusEvent)
        .where(SubOrderStatusEvent.sub_order_id == uuid.UUID(sub_order_id))
        .values(created_at=SubOrderStatusEvent.created_at - timedelta(days=days))
    )
    sub = await db_session.get(SubOrder, uuid.UUID(sub_order_id))
    await db_session.refresh(sub)
    return sub


async def _notes(db_session: AsyncSession, user: User, kind: NotificationType) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.type == kind)
        )
    ).scalar_one()


async def test_buyer_is_reminded_then_parcel_goes_back(
    db_session: AsyncSession, buyer_user: User, vendor_user: User, courier: Courier, paid_parcel_at_point: dict
) -> None:
    sub_id = paid_parcel_at_point["sub_order_id"]
    await _age(db_session, sub_id, 3.2)
    await returns.run_once(db_session)
    await returns.run_once(db_session)
    assert await _notes(db_session, buyer_user, NotificationType.PICKUP_REMINDER) == 1

    await _age(db_session, sub_id, 2)  # 5,2 jours
    await returns.run_once(db_session)
    await _age(db_session, sub_id, 1)  # 6,2 jours : dernier avertissement
    await returns.run_once(db_session)
    assert await _notes(db_session, buyer_user, NotificationType.PICKUP_REMINDER) == 3

    sub = await _age(db_session, sub_id, 1)  # 7,2 jours : retour
    await returns.run_once(db_session)
    await db_session.refresh(sub)
    assert sub.status == OrderStatus.RETURN_PENDING
    assert sub.outbound_courier_id == courier.id and sub.courier_id is None
    assert sub.return_fee == 10000
    assert await _notes(db_session, buyer_user, NotificationType.PARCEL_RETURN) == 1
    assert await _notes(db_session, vendor_user, NotificationType.PARCEL_RETURN) == 1


async def test_return_trip_refunds_the_buyer_and_pays_everyone(
    client: AsyncClient,
    db_session: AsyncSession,
    buyer_user: User,
    admin_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
    manager_user: User,
    paid_parcel_at_point: dict,
) -> None:
    sub_id = paid_parcel_at_point["sub_order_id"]
    total = paid_parcel_at_point["order"]["total"]
    stock_before = product.stock
    await _age(db_session, sub_id, 8)
    await returns.run_once(db_session)

    # Le vendeur ne peut pas déclencher un retour à la main, et trouve un livreur.
    manual = await client.patch(
        f"/orders/sub-orders/{sub_id}/status", json={"status": "return_pending"}, headers=auth_headers(vendor_user)
    )
    assert manual.status_code in (403, 409)
    await client.patch(f"/orders/sub-orders/{sub_id}/courier", json={"courier_id": str(courier.id)}, headers=auth_headers(vendor_user))

    # Au point : QR du livreur scanné par le gestionnaire.
    code = (await client.get(f"/orders/sub-orders/{sub_id}/handoff-code", headers=auth_headers(courier_user))).json()["code"]
    picked = await client.post("/orders/sub-orders/confirm-delivery", json={"code": code}, headers=auth_headers(manager_user))
    assert picked.status_code == 200, picked.text
    assert picked.json()["status"] == "returning"

    # À la boutique : le vendeur scanne le QR du livreur.
    code = (await client.get(f"/orders/sub-orders/{sub_id}/handoff-code", headers=auth_headers(courier_user))).json()["code"]
    back = await client.post("/orders/sub-orders/confirm-delivery", json={"code": code}, headers=auth_headers(vendor_user))
    assert back.status_code == 200, back.text
    assert back.json()["status"] == "returned"

    # Remboursé : 500 000 − 0 (aller offert : non) − 10 000 (retour) ; l'aller (10 000) reste payé.
    assert await _balance(client, buyer_user) == 1_000_000 - total + (product.price - 10000)
    await db_session.refresh(product)
    assert product.stock == stock_before + 1

    courier_wallet = next(
        w for w in (await client.get("/wallets/mine", headers=auth_headers(courier_user))).json() if w["kind"] == "courier"
    )
    assert courier_wallet["balance"]["total"] == 8000 + 8000  # 80 % de l'aller + 80 % du retour
    point_wallet = next(
        w for w in (await client.get("/wallets/mine", headers=auth_headers(manager_user))).json() if w["kind"] == "pickup_point"
    )
    # 50 % de (2 000 + garde 4 j × 200).
    assert point_wallet["balance"]["total"] == 1400
    overview = await _overview(client, admin_user)
    assert overview["is_balanced"] is True
    assert overview["escrow"] == 0

    order = (await client.get(f"/orders/{paid_parcel_at_point['order']['id']}", headers=auth_headers(buyer_user))).json()
    assert order["status"] == "returned"


async def test_late_buyer_can_still_collect_before_the_courier_comes(
    client: AsyncClient,
    db_session: AsyncSession,
    buyer_user: User,
    manager_user: User,
    paid_parcel_at_point: dict,
) -> None:
    sub_id = paid_parcel_at_point["sub_order_id"]
    await _age(db_session, sub_id, 8)
    await returns.run_once(db_session)

    code = (await client.get(f"/orders/sub-orders/{sub_id}/handoff-code", headers=auth_headers(buyer_user))).json()["code"]
    collected = await client.post("/orders/sub-orders/confirm-delivery", json={"code": code}, headers=auth_headers(manager_user))
    assert collected.status_code == 200, collected.text
    assert collected.json()["status"] == "delivered"
