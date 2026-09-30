"""Taille de colis S/M/L/XL : calcul au checkout, supplément L/XL, correction
par le point de retrait, et rémunération du point (taille, garde, bonus)."""

import uuid
from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Product
from app.common.parcel import ParcelSize, parcel_size_for
from app.couriers.models import Courier
from app.delivery.models import DeliveryFeeTier
from app.orders.models import OrderStatus, SubOrder, SubOrderStatusEvent
from app.payments import repository as payments_repository
from app.pickup_points.models import PickupPoint
from app.users.models import User
from app.vendors.models import Vendor
from app.wallets import service as wallets_service
from tests.conftest import auth_headers, scan_handoff
from tests.test_pickup_point_handoff import _ship_pickup_order

KALOUM = (9.5092, -13.7122)
NEAR_KALOUM = (9.5150, -13.7100)


def test_parcel_takes_the_biggest_item_and_grows_with_quantity() -> None:
    assert parcel_size_for([]) == ParcelSize.S
    assert parcel_size_for([("S", 1), ("L", 1)]) == ParcelSize.L
    assert parcel_size_for([("S", 5)]) == ParcelSize.S
    assert parcel_size_for([("S", 6)]) == ParcelSize.M
    assert parcel_size_for([("XL", 9)]) == ParcelSize.XL


async def test_vendor_declares_the_size_of_a_product(
    client: AsyncClient, vendor_user: User, category: Category
) -> None:
    response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Télévision", "price": 900000, "stock": 2, "parcel_size": "XL"},
        headers=auth_headers(vendor_user),
    )
    assert response.status_code == 201
    assert response.json()["parcel_size"] == "XL"
    bad = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "X", "price": 1, "parcel_size": "XXL"},
        headers=auth_headers(vendor_user),
    )
    assert bad.status_code == 422


async def test_bulky_parcel_adds_a_surcharge_to_the_delivery(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product
) -> None:
    db_session.add(DeliveryFeeTier(max_km=3, fee=10000, transit_days=0))
    vendor.latitude, vendor.longitude = KALOUM
    product.parcel_size = "L"
    await db_session.flush()
    await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer_user))

    quote = await client.post(
        "/orders/delivery-quote",
        json={"delivery_type": "home_delivery", "latitude": NEAR_KALOUM[0], "longitude": NEAR_KALOUM[1]},
        headers=auth_headers(buyer_user),
    )
    parcel = quote.json()["vendors"][0]
    assert parcel["parcel_size"] == "L"
    assert parcel["size_surcharge"] == 5000
    assert parcel["delivery_fee"] == 15000


async def _arrive(
    client, buyer_user, vendor_user, courier_user, courier, product, pickup_point, manager_user
) -> str:
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)
    arrival = await scan_handoff(client, manager_user, sub_order_id)
    assert arrival.json()["status"] == OrderStatus.ARRIVED_AT_PICKUP_POINT
    return sub_order_id


async def test_point_corrects_the_size_on_arrival_only(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    product: Product,
    pickup_point: PickupPoint,
) -> None:
    shipped = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)
    too_early = await client.patch(
        f"/orders/sub-orders/{shipped}/parcel-size", json={"parcel_size": "L"}, headers=auth_headers(manager_user)
    )
    assert too_early.status_code == 409

    await scan_handoff(client, manager_user, shipped)
    corrected = await client.patch(
        f"/orders/sub-orders/{shipped}/parcel-size", json={"parcel_size": "L"}, headers=auth_headers(manager_user)
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["parcel_size"] == "L"
    assert corrected.json()["declared_parcel_size"] == "S"
    # Seul le gestionnaire du point peut corriger.
    refused = await client.patch(
        f"/orders/sub-orders/{shipped}/parcel-size", json={"parcel_size": "M"}, headers=auth_headers(vendor_user)
    )
    assert refused.status_code == 403


async def test_point_fee_follows_size_storage_and_volume(
    client: AsyncClient,
    db_session: AsyncSession,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    product: Product,
    pickup_point: PickupPoint,
) -> None:
    settings_row = await payments_repository.get_settings(db_session)
    settings_row.pickup_point_fee_per_parcel = 1500
    settings_row.pickup_fee_m = 2500
    settings_row.pickup_volume_bonus_threshold = 1
    settings_row.pickup_volume_bonus_percent = 10
    await db_session.flush()

    args = (client, buyer_user, vendor_user, courier_user, courier, product, pickup_point, manager_user)
    first = await _arrive(*args)
    second = await _arrive(*args)
    await client.patch(f"/orders/sub-orders/{second}/parcel-size", json={"parcel_size": "M"}, headers=auth_headers(manager_user))

    sub = await db_session.get(SubOrder, uuid.UUID(first))
    await db_session.refresh(sub)
    fee, detail = await wallets_service.pickup_point_fee(db_session, settings_row, sub, pickup_point.id)
    assert (fee, detail) == (1500, "taille S 1500")

    # 1er colis remis ; le 2e a attendu 6 jours au point : 3 jours de garde payés.
    delivered = await scan_handoff(client, manager_user, first)
    assert delivered.json()["status"] == "delivered"
    await db_session.execute(
        update(SubOrderStatusEvent)
        .where(SubOrderStatusEvent.sub_order_id == uuid.UUID(second))
        .values(created_at=SubOrderStatusEvent.created_at - timedelta(days=6))
    )
    sub2 = await db_session.get(SubOrder, uuid.UUID(second))
    await db_session.refresh(sub2)
    fee, detail = await wallets_service.pickup_point_fee(db_session, settings_row, sub2, pickup_point.id)
    # 2500 (M) + 3 × 200 (garde) = 3100, + 10 % de bonus volume (1 colis déjà remis ce mois-ci).
    assert fee == 3100 + 310
    assert detail == "taille M 2500, garde 3 j 600, bonus volume 310"
