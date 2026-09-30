"""Tarif en point de retrait (pourcentage du domicile ou grille dédiée) et
plafonds du « Retrait offert » (montant, distance)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.delivery.models import DeliveryFeeTier, TierKind
from app.payments import repository as payments_repository
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers
from tests.test_payments import _add_to_cart
from tests.test_pickup_offer import NEAR_KALOUM, _fund_vendor, _quote, offer_setup  # noqa: F401


async def _set_pricing(db_session: AsyncSession, mode: str, percent: int = 100) -> None:
    settings_row = await payments_repository.get_settings(db_session)
    settings_row.pickup_pricing_mode = mode
    settings_row.pickup_fee_percent = percent
    await db_session.flush()


async def _home_fee(client: AsyncClient, buyer: User) -> int:
    response = await client.post(
        "/orders/delivery-quote",
        json={"delivery_type": "home_delivery", "latitude": NEAR_KALOUM[0], "longitude": NEAR_KALOUM[1]},
        headers=auth_headers(buyer),
    )
    return response.json()["vendors"][0]["delivery_fee"]


async def test_pickup_fee_is_a_percentage_of_the_home_grid(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product, offer_setup
) -> None:
    vendor.offers_pickup_delivery = False
    await _set_pricing(db_session, "percent", 65)
    await _add_to_cart(client, buyer_user, product)

    parcel = (await _quote(client, buyer_user, offer_setup))["vendors"][0]
    # 10 000 × 65 % = 6 500 GNF ; le domicile ne bouge pas.
    assert parcel["delivery_fee"] == 6500
    assert await _home_fee(client, buyer_user) == 10000


async def test_dedicated_pickup_grid_and_its_fallback(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product, offer_setup
) -> None:
    vendor.offers_pickup_delivery = False
    await _set_pricing(db_session, "grid", 50)
    await _add_to_cart(client, buyer_user, product)

    # Grille dédiée vide : repli sur le pourcentage.
    assert (await _quote(client, buyer_user, offer_setup))["vendors"][0]["delivery_fee"] == 5000

    db_session.add(DeliveryFeeTier(kind=TierKind.PICKUP, max_km=3, fee=4000, transit_days=0))
    await db_session.flush()
    assert (await _quote(client, buyer_user, offer_setup))["vendors"][0]["delivery_fee"] == 4000
    # La grille des points ne touche jamais le domicile.
    assert await _home_fee(client, buyer_user) == 10000


async def test_offer_cap_leaves_the_rest_to_the_buyer(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product, offer_setup
) -> None:
    await _fund_vendor(db_session, vendor, 50000)
    vendor.pickup_offer_min_amount = 0
    vendor.pickup_offer_max_amount = 3000
    await db_session.flush()
    await _add_to_cart(client, buyer_user, product)

    parcel = (await _quote(client, buyer_user, offer_setup))["vendors"][0]
    assert parcel["pickup_offer"] == "partial"
    assert parcel["vendor_delivery_fee"] == 3000
    assert parcel["delivery_fee"] == 7000


async def test_offer_distance_limit(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product, offer_setup
) -> None:
    await _fund_vendor(db_session, vendor, 50000)
    vendor.pickup_offer_min_amount = 0
    # Le point est à ~0,7 km de la boutique.
    vendor.pickup_offer_max_km = 0.2
    await db_session.flush()
    await _add_to_cart(client, buyer_user, product)

    parcel = (await _quote(client, buyer_user, offer_setup))["vendors"][0]
    assert parcel["pickup_offer"] == "out_of_range"
    assert parcel["delivery_fee"] == 10000 and parcel["vendor_delivery_fee"] == 0

    vendor.pickup_offer_max_km = 2
    await db_session.flush()
    parcel = (await _quote(client, buyer_user, offer_setup))["vendors"][0]
    assert parcel["pickup_offer"] == "applied"


async def test_admin_manages_both_grids_and_the_mode(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    home = await client.post("/admin/delivery-fee-tiers", json={"max_km": 5, "fee": 15000}, headers=headers)
    pickup = await client.post(
        "/admin/delivery-fee-tiers", json={"kind": "pickup", "max_km": 5, "fee": 8000, "is_default": True}, headers=headers
    )
    # Même distance, grilles différentes : autorisé ; les unicités sont par grille.
    assert home.status_code == 201 and pickup.status_code == 201, pickup.text
    duplicate = await client.post("/admin/delivery-fee-tiers", json={"kind": "pickup", "max_km": 5, "fee": 1}, headers=headers)
    assert duplicate.status_code == 409
    kinds = sorted(t["kind"] for t in (await client.get("/admin/delivery-fee-tiers", headers=headers)).json())
    assert kinds == ["home", "pickup"]

    assert (await client.get("/admin/delivery-fee-tiers/settings", headers=headers)).json() == {
        "pickup_pricing_mode": "percent",
        "pickup_fee_percent": 100,
    }
    updated = await client.patch(
        "/admin/delivery-fee-tiers/settings", json={"pickup_pricing_mode": "grid", "pickup_fee_percent": 70}, headers=headers
    )
    assert updated.json() == {"pickup_pricing_mode": "grid", "pickup_fee_percent": 70}


async def test_vendor_sets_and_clears_offer_caps(client: AsyncClient, vendor_user: User, vendor: Vendor) -> None:
    headers = auth_headers(vendor_user)
    response = await client.patch(
        "/vendors/me", json={"pickup_offer_max_amount": 15000, "pickup_offer_max_km": 12.5}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["pickup_offer_max_amount"] == 15000
    cleared = await client.patch("/vendors/me", json={"pickup_offer_max_amount": None}, headers=headers)
    assert cleared.json()["pickup_offer_max_amount"] is None
    assert cleared.json()["pickup_offer_max_km"] == 12.5
