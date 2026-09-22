"""Tests for the delivery fee grid (distance tiers), the checkout quote and
fees/delivery estimates frozen on sub-orders at checkout."""

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.delivery.models import DeliveryFeeTier
from app.delivery.service import compute_fee, compute_transit_days
from app.pickup_points.models import PickupPoint
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers, make_vendor

# Kaloum ↔ Ratoma ≈ 10 km ; Kaloum ↔ Kaloum voisin ≈ 1 km.
KALOUM = (9.5092, -13.7122)
NEAR_KALOUM = (9.5150, -13.7100)
RATOMA = (9.5900, -13.6500)

TIERS = [
    DeliveryFeeTier(max_km=3, fee=10000, transit_days=0),
    DeliveryFeeTier(max_km=8, fee=20000, transit_days=1),
    DeliveryFeeTier(max_km=None, fee=35000, transit_days=3),
]


def test_compute_fee_picks_the_tier_covering_the_distance() -> None:
    assert compute_fee(TIERS, KALOUM, NEAR_KALOUM) == 10000
    assert compute_fee(TIERS, KALOUM, RATOMA) == 35000  # ~11 km : au-delà de 8 km


def test_compute_fee_falls_back_when_a_position_is_missing() -> None:
    assert compute_fee(TIERS, KALOUM, (None, None)) == 35000
    assert compute_fee(TIERS, (None, None), NEAR_KALOUM) == 35000


def test_compute_fee_without_catch_all_uses_the_dearest_tier() -> None:
    bounded = [DeliveryFeeTier(max_km=3, fee=10000, transit_days=0), DeliveryFeeTier(max_km=8, fee=20000, transit_days=1)]
    assert compute_fee(bounded, KALOUM, RATOMA) == 20000
    assert compute_fee(bounded, KALOUM, (None, None)) == 20000


def test_compute_fee_is_free_without_any_tier() -> None:
    assert compute_fee([], KALOUM, RATOMA) == 0


def test_compute_transit_days_picks_the_tier_covering_the_distance() -> None:
    assert compute_transit_days(TIERS, KALOUM, NEAR_KALOUM) == 0
    assert compute_transit_days(TIERS, KALOUM, RATOMA) == 3  # ~11 km : au-delà de 8 km


def test_compute_transit_days_falls_back_when_a_position_is_missing() -> None:
    assert compute_transit_days(TIERS, KALOUM, (None, None)) == 3
    assert compute_transit_days(TIERS, (None, None), NEAR_KALOUM) == 3


def test_compute_transit_days_without_catch_all_uses_the_slowest_tier() -> None:
    bounded = [DeliveryFeeTier(max_km=3, fee=10000, transit_days=0), DeliveryFeeTier(max_km=8, fee=20000, transit_days=1)]
    assert compute_transit_days(bounded, KALOUM, RATOMA) == 1
    assert compute_transit_days(bounded, KALOUM, (None, None)) == 1


def test_compute_transit_days_uses_the_default_without_any_tier() -> None:
    assert compute_transit_days([], KALOUM, RATOMA) == 1


async def _add_tiers(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            DeliveryFeeTier(max_km=3, fee=10000, transit_days=0),
            DeliveryFeeTier(max_km=None, fee=35000, transit_days=3),
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
    assert created.json()["transit_days"] == 1  # défaut sans le champ
    tier_id = created.json()["id"]

    await client.post("/admin/delivery-fee-tiers", json={"max_km": None, "fee": 40000, "transit_days": 3}, headers=headers)
    listing = await client.get("/admin/delivery-fee-tiers", headers=headers)
    assert [t["max_km"] for t in listing.json()] == [5, None]
    assert [t["transit_days"] for t in listing.json()] == [1, 3]

    patched = await client.patch(
        f"/admin/delivery-fee-tiers/{tier_id}", json={"fee": 18000, "transit_days": 0}, headers=headers
    )
    assert patched.status_code == 200 and patched.json()["fee"] == 18000 and patched.json()["transit_days"] == 0

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

    # Même grille que les frais : boutique proche (palier 3 km, 0 jour de
    # trajet) contre boutique éloignée (palier « au-delà », 3 jours) —
    # préparation à 1 jour pour les deux vendeurs (défaut, voir Vendor.preparation_days).
    today = date.today()
    estimates = {v["shop_name"]: (v["estimated_delivery_min"], v["estimated_delivery_max"]) for v in body["vendors"]}
    assert estimates["Boutique Test"] == (str(today + timedelta(days=1)), str(today + timedelta(days=2)))
    assert estimates["Autre Boutique"] == (str(today + timedelta(days=4)), str(today + timedelta(days=5)))

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
    assert by_shop["Boutique Test"]["estimated_delivery_min"] == str(today + timedelta(days=1))
    assert by_shop["Autre Boutique"]["delivery_fee"] == 35000
    assert by_shop["Autre Boutique"]["estimated_delivery_min"] == str(today + timedelta(days=4))


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


async def test_tier_label_is_optional_trimmed_and_editable(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    created = await client.post(
        "/admin/delivery-fee-tiers", json={"max_km": 25, "fee": 50000, "label": "  Périphérie de Conakry  "}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["label"] == "Périphérie de Conakry"
    tier_id = created.json()["id"]

    # Modifier le tarif seul ne touche pas au libellé ; un libellé vide l'efface.
    kept = await client.patch(f"/admin/delivery-fee-tiers/{tier_id}", json={"fee": 55000}, headers=headers)
    assert kept.json()["label"] == "Périphérie de Conakry"
    cleared = await client.patch(f"/admin/delivery-fee-tiers/{tier_id}", json={"label": "   "}, headers=headers)
    assert cleared.json()["label"] is None


async def test_tier_can_become_catch_all_and_conflicts_are_kept_on_update(
    client: AsyncClient, admin_user: User
) -> None:
    headers = auth_headers(admin_user)
    first = (await client.post("/admin/delivery-fee-tiers", json={"max_km": 5, "fee": 1000}, headers=headers)).json()
    second = (await client.post("/admin/delivery-fee-tiers", json={"max_km": 10, "fee": 2000}, headers=headers)).json()

    clash = await client.patch(f"/admin/delivery-fee-tiers/{second['id']}", json={"max_km": 5}, headers=headers)
    assert clash.status_code == 409
    same = await client.patch(f"/admin/delivery-fee-tiers/{first['id']}", json={"max_km": 5, "fee": 1500}, headers=headers)
    assert same.status_code == 200 and same.json()["fee"] == 1500

    beyond = await client.patch(f"/admin/delivery-fee-tiers/{second['id']}", json={"max_km": None}, headers=headers)
    assert beyond.status_code == 200 and beyond.json()["max_km"] is None


async def test_tier_transit_days_cannot_be_cleared(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    tier = (await client.post("/admin/delivery-fee-tiers", json={"max_km": 5, "fee": 1000}, headers=headers)).json()
    cleared = await client.patch(
        f"/admin/delivery-fee-tiers/{tier['id']}", json={"transit_days": None}, headers=headers
    )
    assert cleared.status_code == 409


async def test_unknown_tier_update_and_delete_are_404(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.patch(f"/admin/delivery-fee-tiers/{missing}", json={"fee": 1}, headers=headers)).status_code == 404
    assert (await client.delete(f"/admin/delivery-fee-tiers/{missing}", headers=headers)).status_code == 404
