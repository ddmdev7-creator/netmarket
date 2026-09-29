"""« Retrait offert » par le vendeur et palier de livraison par défaut
(position de l'acheteur inconnue)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.delivery.models import DeliveryFeeTier
from app.delivery.service import compute_fee, compute_transit_days
from app.orders import repository as orders_repository
from app.orders.models import OrderStatus
from app.pickup_points.models import PickupPoint
from app.users.models import User
from app.vendors.models import Vendor
from app.wallets import repository as wallets_repository
from app.wallets import service as wallets_service
from app.wallets.models import AccountKind, TransactionKind
from tests.conftest import auth_headers
from tests.test_payments import _add_to_cart, _sign_webhook, _stub_djomy_initiate, _webhook_payload

KALOUM = (9.5092, -13.7122)
NEAR_KALOUM = (9.5150, -13.7100)


def test_unknown_position_uses_the_default_tier() -> None:
    tiers = [
        DeliveryFeeTier(max_km=3, fee=10000, transit_days=0),
        DeliveryFeeTier(max_km=8, fee=20000, transit_days=1, is_default=True),
        DeliveryFeeTier(max_km=None, fee=150000, transit_days=3),
    ]
    assert compute_fee(tiers, KALOUM, (None, None)) == 20000
    assert compute_transit_days(tiers, KALOUM, (None, None)) == 1
    # Sans palier par défaut : le palier « au-delà », comme avant.
    tiers[1].is_default = False
    assert compute_fee(tiers, KALOUM, (None, None)) == 150000


async def test_only_one_default_tier(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    first = (await client.post("/admin/delivery-fee-tiers", json={"max_km": 5, "fee": 15000, "is_default": True}, headers=headers)).json()
    second = (await client.post("/admin/delivery-fee-tiers", json={"max_km": 10, "fee": 25000}, headers=headers)).json()
    response = await client.patch(f"/admin/delivery-fee-tiers/{second['id']}", json={"is_default": True}, headers=headers)
    assert response.status_code == 200, response.text
    tiers = {t["id"]: t for t in (await client.get("/admin/delivery-fee-tiers", headers=headers)).json()}
    assert tiers[second["id"]]["is_default"] is True
    assert tiers[first["id"]]["is_default"] is False


@pytest.fixture
async def offer_setup(db_session: AsyncSession, vendor: Vendor) -> PickupPoint:
    db_session.add_all(
        [
            DeliveryFeeTier(max_km=3, fee=10000, transit_days=0),
            DeliveryFeeTier(max_km=None, fee=35000, transit_days=3),
        ]
    )
    vendor.latitude, vendor.longitude = KALOUM
    vendor.offers_pickup_delivery = True
    vendor.pickup_offer_min_amount = 100000
    point = PickupPoint(name="Point Proche", zone="Kaloum", latitude=NEAR_KALOUM[0], longitude=NEAR_KALOUM[1])
    db_session.add(point)
    await db_session.flush()
    return point


async def _fund_vendor(db_session: AsyncSession, vendor: Vendor, amount: int) -> None:
    account = await wallets_repository.get_or_create_account(db_session, AccountKind.VENDOR, vendor.id)
    revenue = await wallets_repository.get_or_create_account(db_session, AccountKind.PLATFORM_REVENUE)
    await wallets_service._post(
        db_session,
        kind=TransactionKind.WALLET_TOPUP,
        key=f"test-fund:{vendor.id}:{amount}",
        description="Solde de test",
        lines=[(account, -amount, None), (revenue, amount, None)],
    )


def _pickup_payload(point: PickupPoint, **extra) -> dict:
    return {"delivery_type": "pickup_point", "pickup_point_id": str(point.id), **extra}


async def _quote(client: AsyncClient, buyer: User, point: PickupPoint) -> dict:
    response = await client.post("/orders/delivery-quote", json=_pickup_payload(point), headers=auth_headers(buyer))
    assert response.status_code == 200, response.text
    return response.json()


async def test_offer_needs_enough_balance(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product, offer_setup
) -> None:
    await _add_to_cart(client, buyer_user, product)

    quote = await _quote(client, buyer_user, offer_setup)
    parcel = quote["vendors"][0]
    assert parcel["pickup_offer"] == "unavailable"
    assert parcel["delivery_fee"] == 10000 and quote["delivery_total"] == 10000

    await _fund_vendor(db_session, vendor, 10000)
    quote = await _quote(client, buyer_user, offer_setup)
    parcel = quote["vendors"][0]
    assert parcel["pickup_offer"] == "applied"
    assert parcel["delivery_fee"] == 0 and parcel["vendor_delivery_fee"] == 10000
    assert quote["total"] == product.price

    # À domicile : jamais offert.
    home = await client.post(
        "/orders/delivery-quote",
        json={"delivery_type": "home_delivery", "latitude": NEAR_KALOUM[0], "longitude": NEAR_KALOUM[1]},
        headers=auth_headers(buyer_user),
    )
    assert home.json()["vendors"][0]["pickup_offer"] is None


async def test_offer_below_minimum_tells_what_is_missing(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product, offer_setup
) -> None:
    await _fund_vendor(db_session, vendor, 50000)
    vendor.pickup_offer_min_amount = product.price + 20000
    await db_session.flush()
    await _add_to_cart(client, buyer_user, product)
    parcel = (await _quote(client, buyer_user, offer_setup))["vendors"][0]
    assert parcel["pickup_offer"] == "below_minimum"
    assert parcel["pickup_offer_missing"] == 20000
    assert parcel["delivery_fee"] == 10000


async def test_offered_delivery_is_charged_to_the_vendor_on_delivery(
    client: AsyncClient,
    db_session: AsyncSession,
    buyer_user: User,
    vendor_user: User,
    vendor: Vendor,
    product: Product,
    admin_user: User,
    offer_setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fund_vendor(db_session, vendor, 30000)
    await _add_to_cart(client, buyer_user, product)
    _stub_djomy_initiate(monkeypatch)
    checkout = await client.post(
        "/orders/checkout",
        json=_pickup_payload(offer_setup, delivery_address="Point Proche", payment_method="online", payer_phone="00224623707722"),
        headers=auth_headers(buyer_user),
    )
    assert checkout.status_code == 201, checkout.text
    order = checkout.json()
    assert order["total"] == product.price
    sub = order["sub_orders"][0]
    assert sub["delivery_fee"] == 0 and sub["vendor_delivery_fee"] == 10000

    body = _webhook_payload(order["id"], "payment.success", "SUCCESS")
    await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": _sign_webhook(monkeypatch, body), "Content-Type": "application/json"},
    )

    # Les 10 000 GNF engagés ne sont pas retirables tant que le colis est en route.
    wallets = (await client.get("/wallets/mine", headers=auth_headers(vendor_user))).json()
    wallet = next(w for w in wallets if w["kind"] == "vendor")
    assert wallet["committed_offers"] == 10000
    await client.put(
        f"/wallets/{wallet['id']}/payout-method",
        json={"payout_provider": "OM", "payout_account_number": "622000000", "payout_beneficiary_name": "Awa"},
        headers=auth_headers(vendor_user),
    )
    too_much = await client.post(f"/wallets/{wallet['id']}/withdrawals", json={"amount": 25000}, headers=auth_headers(vendor_user))
    assert too_much.status_code == 409
    assert "réservés" in too_much.json()["detail"]

    # Livraison : la course est prélevée sur le solde du vendeur.
    sub_order = await orders_repository.get_sub_order_by_id(db_session, sub["id"])
    sub_order.status = OrderStatus.DELIVERED
    await db_session.flush()
    await wallets_service.settle_sub_order(db_session, sub_order.order, sub_order)
    balance = await wallets_service.get_wallet_balance(db_session, AccountKind.VENDOR, vendor.id)
    net = sub["amount"] - sub["commission"]
    assert balance.available == 30000 - 10000
    assert balance.total == 30000 - 10000 + net
    assert await wallets_service.committed_pickup_offers(db_session, vendor.id) == 0
    overview = (await client.get("/admin/finance/overview", headers=auth_headers(admin_user))).json()
    assert overview["is_balanced"] is True
