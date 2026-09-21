"""Tests for the delivery fee grid (distance tiers), the checkout quote and
fees frozen on sub-orders at checkout."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.delivery.models import DeliveryFeeTier
from app.delivery.service import compute_fee
from app.pickup_points.models import PickupPoint
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers, make_vendor

# Kaloum ↔ Ratoma ≈ 10 km ; Kaloum ↔ Kaloum voisin ≈ 1 km.
KALOUM = (9.5092, -13.7122)
NEAR_KALOUM = (9.5150, -13.7100)
RATOMA = (9.5900, -13.6500)

TIERS = [
    DeliveryFeeTier(max_km=3, fee=10000),
    DeliveryFeeTier(max_km=8, fee=20000),
    DeliveryFeeTier(max_km=None, fee=35000),
]


def test_compute_fee_picks_the_tier_covering_the_distance() -> None:
    assert compute_fee(TIERS, KALOUM, NEAR_KALOUM) == 10000
    assert compute_fee(TIERS, KALOUM, RATOMA) == 35000  # ~11 km : au-delà de 8 km


def test_compute_fee_falls_back_when_a_position_is_missing() -> None:
    assert compute_fee(TIERS, KALOUM, (None, None)) == 35000
    assert compute_fee(TIERS, (None, None), NEAR_KALOUM) == 35000


def test_compute_fee_without_catch_all_uses_the_dearest_tier() -> None:
    bounded = [DeliveryFeeTier(max_km=3, fee=10000), DeliveryFeeTier(max_km=8, fee=20000)]
    assert compute_fee(bounded, KALOUM, RATOMA) == 20000
    assert compute_fee(bounded, KALOUM, (None, None)) == 20000


def test_compute_fee_is_free_without_any_tier() -> None:
    assert compute_fee([], KALOUM, RATOMA) == 0


async def _add_tiers(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            DeliveryFeeTier(max_km=3, fee=10000),
            DeliveryFeeTier(max_km=None, fee=35000),
        ]
    )
    await db_session.flush()


async def _add_to_cart(client: AsyncClient, user: User, product: Product) -> None:
    response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(user)
    )
    assert response.status_code == 201


async def test_admin_manages_tiers(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    created = await client.post("/admin/delivery-fee-tiers", json={"max_km": 5, "fee": 15000}, headers=headers)
    assert created.status_code == 201
    tier_id = created.json()["id"]

    await client.post("/admin/delivery-fee-tiers", json={"max_km": None, "fee": 40000}, headers=headers)
    listing = await client.get("/admin/delivery-fee-tiers", headers=headers)
    assert [t["max_km"] for t in listing.json()] == [5, None]

    patched = await client.patch(f"/admin/delivery-fee-tiers/{tier_id}", json={"fee": 18000}, headers=headers)
    assert patched.status_code == 200 and patched.json()["fee"] == 18000

    deleted = await client.delete(f"/admin/delivery-fee-tiers/{tier_id}", headers=headers)
    assert deleted.status_code == 200
    assert len((await client.get("/admin/delivery-fee-tiers", headers=headers)).json()) == 1


async def test_duplicate_tiers_are_rejected(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    await client.post("/admin/delivery-fee-tiers", json={"max_km": 5, "fee": 15000}, headers=headers)
    await client.post("/admin/delivery-fee-tiers", json={"max_km": None, "fee": 40000}, headers=headers)
    assert (
        await client.post("/admin/delivery-fee-tiers", json={"max_km": 5, "fee": 1}, headers=headers)
    ).status_code == 409
    assert (
        await client.post("/admin/delivery-fee-tiers", json={"max_km": None, "fee": 1}, headers=headers)
    ).status_code == 409


async def test_tiers_are_admin_only(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/delivery-fee-tiers", headers=auth_headers(buyer_user))
    assert response.status_code == 403


async def test_quote_and_checkout_charge_a_fee_per_vendor_parcel(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, product: Product, vendor: Vendor, category
) -> None:
    await _add_tiers(db_session)
    vendor.latitude, vendor.longitude = KALOUM
    other_user, other_vendor = await make_vendor(db_session, phone="+224620000099", shop_name="Autre Boutique")
    other_vendor.latitude, other_vendor.longitude = RATOMA
    other_product = Product(vendor_id=other_vendor.id, category_id=category.id, name="Sac", price=100000, stock=5)
    db_session.add(other_product)
    await db_session.flush()
    await _add_to_cart(client, buyer_user, product)
    await _add_to_cart(client, buyer_user, other_product)

    destination = {"latitude": NEAR_KALOUM[0], "longitude": NEAR_KALOUM[1]}
    quote = await client.post("/orders/delivery-quote", json=destination, headers=auth_headers(buyer_user))
    assert quote.status_code == 200
    body = quote.json()
    fees = {v["shop_name"]: v["delivery_fee"] for v in body["vendors"]}
    assert fees == {"Boutique Test": 10000, "Autre Boutique": 35000}
    assert body["items_total"] == 600000
    assert body["delivery_total"] == 45000
    assert body["total"] == 645000

    checkout = await client.post(
        "/orders/checkout",
        json={"delivery_address": "Kaloum, près du marché", **destination},
        headers=auth_headers(buyer_user),
    )
    assert checkout.status_code == 201
    order = checkout.json()
    assert order["total"] == 645000
    by_shop = {so["shop_name"]: so for so in order["sub_orders"]}
    assert by_shop["Boutique Test"]["delivery_fee"] == 10000
    assert by_shop["Boutique Test"]["amount"] == 500000
    assert by_shop["Autre Boutique"]["delivery_fee"] == 35000


async def test_commission_ignores_the_delivery_fee(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, product: Product, vendor: Vendor
) -> None:
    await _add_tiers(db_session)
    vendor.commission_rate = 10
    await _add_to_cart(client, buyer_user, product)
    response = await client.post(
        "/orders/checkout", json={"delivery_address": "Kaloum, près du marché"}, headers=auth_headers(buyer_user)
    )
    sub_order = response.json()["sub_orders"][0]
    assert sub_order["commission"] == 50000  # 10 % de 500 000, pas de 535 000
    assert sub_order["delivery_fee"] == 35000  # positions inconnues : palier de repli


async def test_pickup_point_fee_uses_the_points_own_position(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, product: Product, vendor: Vendor
) -> None:
    await _add_tiers(db_session)
    vendor.latitude, vendor.longitude = KALOUM
    point = PickupPoint(name="Point Proche", zone="Kaloum", latitude=NEAR_KALOUM[0], longitude=NEAR_KALOUM[1])
    db_session.add(point)
    await db_session.flush()
    await _add_to_cart(client, buyer_user, product)

    # Les coordonnées envoyées par le client sont ignorées pour un point de retrait.
    payload = {
        "delivery_type": "pickup_point",
        "pickup_point_id": str(point.id),
        "latitude": RATOMA[0],
        "longitude": RATOMA[1],
    }
    quote = await client.post("/orders/delivery-quote", json=payload, headers=auth_headers(buyer_user))
    assert quote.json()["delivery_total"] == 10000


async def test_quote_requires_a_point_for_pickup_and_a_non_empty_cart(
    client: AsyncClient, buyer_user: User, product: Product
) -> None:
    empty = await client.post("/orders/delivery-quote", json={}, headers=auth_headers(buyer_user))
    assert empty.status_code == 409
    await _add_to_cart(client, buyer_user, product)
    no_point = await client.post(
        "/orders/delivery-quote", json={"delivery_type": "pickup_point"}, headers=auth_headers(buyer_user)
    )
    assert no_point.status_code == 409
