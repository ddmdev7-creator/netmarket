"""Tests du grand livre : répartition à la livraison, soldes, retraits, compte principal."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User, UserRole
from app.vendors.models import Vendor
from tests.conftest import auth_headers, make_user
from tests.test_payments import (
    CHECKOUT_PAYLOAD,
    _add_to_cart,
    _checkout_and_pay_online,
    _sign_webhook,
    _stub_djomy_payout,
    _stub_djomy_status,
    _webhook_payload,
)


async def _deliver(client: AsyncClient, vendor_user: User, courier: Courier, courier_user: User, order_id: str) -> dict:
    order = (await client.get(f"/admin/orders/{order_id}", headers=auth_headers(await _admin(client)))).json()
    sub_order_id = order["sub_orders"][0]["id"]
    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for status in ("confirmed", "preparing", "shipped"):
        response = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": status}, headers=vendor_headers
        )
        assert response.status_code == 200, response.text
    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status", json={"status": "delivered"}, headers=auth_headers(courier_user)
    )
    assert response.status_code == 200, response.text
    return order["sub_orders"][0]


@pytest.fixture(autouse=True)
def _admin_for_helpers(admin_user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    """Les helpers appellent des routes admin : le compte admin du test leur
    est exposé ici plutôt que passé partout en paramètre."""
    monkeypatch.setitem(_STATE, "admin", admin_user)


_STATE: dict[str, User] = {}


async def _admin(client: AsyncClient) -> User:
    return _STATE["admin"]


async def _set_settings(client: AsyncClient, **overrides) -> None:
    settings = {
        "courier_delivery_share_percent": 80,
        "pickup_point_fee_per_parcel": 2000,
        "earnings_hold_days": 3,
        "withdrawal_fee_percent": 0,
        "min_withdrawal_amount": 10000,
        **overrides,
    }
    response = await client.put("/admin/finance/settings", json=settings, headers=auth_headers(await _admin(client)))
    assert response.status_code == 200, response.text


async def _wallet(client: AsyncClient, user: User, kind: str) -> dict:
    wallets = (await client.get("/wallets/mine", headers=auth_headers(user))).json()
    return next(w for w in wallets if w["kind"] == kind)


async def _overview(client: AsyncClient) -> dict:
    return (await client.get("/admin/finance/overview", headers=auth_headers(await _admin(client)))).json()


async def test_delivery_of_online_order_splits_the_money(
    client: AsyncClient,
    db_session: AsyncSession,
    buyer_user: User,
    vendor_user: User,
    vendor: Vendor,
    product: Product,
    courier: Courier,
    courier_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor.commission_rate = 10
    await db_session.flush()
    await _set_settings(client)
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)

    overview = await _overview(client)
    total = overview["treasury"]
    assert overview["escrow"] == total > 0

    sub = await _deliver(client, vendor_user, courier, courier_user, order_id)

    vendor_wallet = await _wallet(client, vendor_user, "vendor")
    assert vendor_wallet["balance"]["total"] == sub["amount"] - sub["commission"]
    # Délai de sécurité de 3 jours : rien n'est encore retirable.
    assert vendor_wallet["balance"]["available"] == 0
    assert vendor_wallet["balance"]["pending"] == sub["amount"] - sub["commission"]

    courier_share = round(sub["delivery_fee"] * 0.8)
    if courier_share:
        courier_wallet = await _wallet(client, courier_user, "courier")
        assert courier_wallet["balance"]["total"] == courier_share

    overview = await _overview(client)
    assert overview["escrow"] == 0
    assert overview["platform_revenue"] == sub["commission"] + sub["delivery_fee"] - courier_share
    assert overview["is_balanced"] is True


async def test_payment_webhook_replayed_is_recorded_once(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    first = (await _overview(client))["treasury"]

    body = _webhook_payload(order_id, "payment.success", "SUCCESS")
    signature = _sign_webhook(monkeypatch, body)
    await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )

    assert (await _overview(client))["treasury"] == first


async def test_cash_on_delivery_stays_out_of_the_ledger(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _add_to_cart(client, buyer_user, product)
    checkout = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    await _deliver(client, vendor_user, courier, courier_user, checkout.json()["id"])

    assert (await _wallet(client, vendor_user, "vendor"))["balance"]["total"] == 0
    assert (await _overview(client))["treasury"] == 0


async def test_refund_takes_the_money_out_of_the_treasury(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    _stub_djomy_status(monkeypatch)
    _stub_djomy_payout(monkeypatch, item_id="refund-1")
    await client.post(f"/orders/{order_id}/cancel", headers=auth_headers(buyer_user))

    body = json.dumps({"eventType": "payout.success", "data": {"payout": {"payoutId": "refund-1"}}}).encode()
    signature = _sign_webhook(monkeypatch, body)
    await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )

    overview = await _overview(client)
    assert overview["treasury"] == 0
    assert overview["escrow"] == 0
    assert overview["total_refunded"] == overview["total_captured"] > 0


async def _vendor_with_available_balance(
    client, buyer_user, vendor_user, product, courier, courier_user, monkeypatch
) -> dict:
    await _set_settings(client, earnings_hold_days=0, withdrawal_fee_percent=2)
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    await _deliver(client, vendor_user, courier, courier_user, order_id)
    wallet = await _wallet(client, vendor_user, "vendor")
    assert wallet["balance"]["available"] > 0
    return wallet


async def test_withdrawal_requires_a_payout_method_and_enough_balance(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wallet = await _vendor_with_available_balance(
        client, buyer_user, vendor_user, product, courier, courier_user, monkeypatch
    )
    headers = auth_headers(vendor_user)

    no_method = await client.post(f"/wallets/{wallet['id']}/withdrawals", json={"amount": 20000}, headers=headers)
    assert no_method.status_code == 409

    await client.put(
        f"/wallets/{wallet['id']}/payout-method",
        json={"payout_provider": "OM", "payout_account_number": "622000000", "payout_beneficiary_name": "Awa Camara"},
        headers=headers,
    )
    too_much = await client.post(
        f"/wallets/{wallet['id']}/withdrawals",
        json={"amount": wallet["balance"]["available"] + 1},
        headers=headers,
    )
    assert too_much.status_code == 409


async def test_full_withdrawal_cycle_through_djomy(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wallet = await _vendor_with_available_balance(
        client, buyer_user, vendor_user, product, courier, courier_user, monkeypatch
    )
    headers = auth_headers(vendor_user)
    await client.put(
        f"/wallets/{wallet['id']}/payout-method",
        json={"payout_provider": "OM", "payout_account_number": "622000000", "payout_beneficiary_name": "Awa Camara"},
        headers=headers,
    )
    before = (await _overview(client))["treasury"]

    response = await client.post(f"/wallets/{wallet['id']}/withdrawals", json={"amount": 100000}, headers=headers)
    assert response.status_code == 201, response.text
    withdrawal = response.json()
    assert (withdrawal["fee"], withdrawal["net_amount"]) == (2000, 98000)
    after_request = await _wallet(client, vendor_user, "vendor")
    assert after_request["balance"]["available"] == wallet["balance"]["available"] - 100000
    assert after_request["withdrawals_in_progress"] == 100000

    sent = {}

    async def fake_create_payout(**kwargs) -> dict:
        sent.update(kwargs)
        return {"order_id": "po-1", "payout_id": "item-1", "total_amount_to_pay": 99500}

    monkeypatch.setattr("app.payments.djomy_client.create_payout", fake_create_payout)
    admin_headers = auth_headers(await _admin(client))
    approved = await client.post(f"/admin/finance/withdrawals/{withdrawal['id']}/approve", headers=admin_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "processing"
    assert (sent["amount"], sent["provider_code"], sent["account_number"]) == (98000, "OM", "622000000")

    body = json.dumps(
        {"eventType": "payout.success", "data": {"payout": {"payoutId": "item-1", "totalAmountToPay": 99500}}}
    ).encode()
    signature = _sign_webhook(monkeypatch, body)
    await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )

    [paid] = (await client.get(f"/wallets/{wallet['id']}/withdrawals", headers=headers)).json()
    assert paid["status"] == "paid"
    overview = await _overview(client)
    assert overview["treasury"] == before - 99500
    assert overview["withdrawals_reserved"] == 0
    assert overview["total_paid_out"] == 99500
    assert overview["is_balanced"] is True


async def test_rejected_withdrawal_gives_the_money_back(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wallet = await _vendor_with_available_balance(
        client, buyer_user, vendor_user, product, courier, courier_user, monkeypatch
    )
    headers = auth_headers(vendor_user)
    await client.put(
        f"/wallets/{wallet['id']}/payout-method",
        json={"payout_provider": "MOMO", "payout_account_number": "664000000", "payout_beneficiary_name": "Awa"},
        headers=headers,
    )
    withdrawal = (
        await client.post(f"/wallets/{wallet['id']}/withdrawals", json={"amount": 50000}, headers=headers)
    ).json()

    rejected = await client.post(
        f"/admin/finance/withdrawals/{withdrawal['id']}/reject",
        json={"reason": "Numéro à vérifier"},
        headers=auth_headers(await _admin(client)),
    )

    assert rejected.json()["status"] == "rejected"
    assert (await _wallet(client, vendor_user, "vendor"))["balance"]["available"] == wallet["balance"]["available"]


async def test_wallet_is_private_to_its_owner(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User
) -> None:
    wallet = await _wallet(client, vendor_user, "vendor")
    other = await make_user(db_session, phone="+224620009999", role=UserRole.VENDOR)

    response = await client.get(f"/wallets/{wallet['id']}/entries", headers=auth_headers(other))

    assert response.status_code == 403


async def test_finance_endpoints_are_admin_only(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/finance/overview", headers=auth_headers(buyer_user))

    assert response.status_code == 403
