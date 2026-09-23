"""Tests NdjouriBank : recharge Djomy, paiement avec le solde, remboursements sur le solde."""

import pytest
from httpx import AsyncClient

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers, scan_handoff
from tests.test_payments import (
    _add_to_cart,
    _checkout_and_pay_online,
    _sign_webhook,
    _stub_djomy_payout,
    _stub_djomy_status,
    _webhook_payload,
)

WALLET_CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "wallet"}


async def _settings(client: AsyncClient, admin: User, **overrides) -> None:
    settings = {
        "courier_delivery_share_percent": 80,
        "pickup_point_fee_per_parcel": 2000,
        "earnings_hold_days": 3,
        "withdrawal_fee_percent": 0,
        "min_withdrawal_amount": 10000,
        "buyer_wallet_enabled": True,
        "wallet_topup_min": 5000,
        "wallet_topup_max": 2_000_000,
        "wallet_max_balance": 5_000_000,
        **overrides,
    }
    response = await client.put("/admin/finance/settings", json=settings, headers=auth_headers(admin))
    assert response.status_code == 200, response.text


def _stub_initiate(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls: dict = {}

    async def fake_initiate(**kwargs) -> tuple[str, str]:
        calls.update(kwargs)
        return "txn-topup", "https://portal.djomy.test/pay"

    monkeypatch.setattr("app.payments.djomy_client.initiate_gateway_payment", fake_initiate)
    return calls


async def _webhook(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, reference: str, event: str, status: str):
    body = _webhook_payload(reference, event, status)
    return await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": _sign_webhook(monkeypatch, body), "Content-Type": "application/json"},
    )


async def _top_up(client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch, amount: int) -> dict:
    _stub_initiate(monkeypatch)
    response = await client.post("/ndjouribank/topups", json={"amount": amount}, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    topup = response.json()["topup"]
    await _webhook(client, monkeypatch, topup["id"], "payment.success", "SUCCESS")
    return topup


async def _balance(client: AsyncClient, user: User) -> int:
    return (await client.get("/ndjouribank", headers=auth_headers(user))).json()["balance"]


async def _overview(client: AsyncClient, admin: User) -> dict:
    return (await client.get("/admin/finance/overview", headers=auth_headers(admin))).json()


async def test_topup_is_closed_until_the_admin_enables_it(
    client: AsyncClient, buyer_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_initiate(monkeypatch)
    wallet = (await client.get("/ndjouribank", headers=auth_headers(buyer_user))).json()
    assert wallet["enabled"] is False
    assert wallet["balance"] == 0
    response = await client.post("/ndjouribank/topups", json={"amount": 10000}, headers=auth_headers(buyer_user))
    assert response.status_code == 409


async def test_topup_confirmed_by_webhook_credits_the_balance_once(
    client: AsyncClient, buyer_user: User, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _settings(client, admin_user)
    calls = _stub_initiate(monkeypatch)
    response = await client.post(
        "/ndjouribank/topups", json={"amount": 50000, "payer_phone": "622000000"}, headers=auth_headers(buyer_user)
    )
    assert response.status_code == 201, response.text
    started = response.json()
    assert started["redirect_url"] == "https://portal.djomy.test/pay"
    assert started["topup"]["status"] == "pending"
    assert calls["reference"] == started["topup"]["id"]
    assert calls["payer_number"] == "622000000"
    assert await _balance(client, buyer_user) == 0

    topup_id = started["topup"]["id"]
    await _webhook(client, monkeypatch, topup_id, "payment.success", "SUCCESS")
    await _webhook(client, monkeypatch, topup_id, "payment.success", "SUCCESS")

    assert await _balance(client, buyer_user) == 50000
    [topup] = (await client.get("/ndjouribank/topups", headers=auth_headers(buyer_user))).json()
    assert topup["status"] == "paid"
    entries = (await client.get("/ndjouribank/entries", headers=auth_headers(buyer_user))).json()["items"]
    assert [(e["kind"], e["amount"]) for e in entries] == [("wallet_topup", 50000)]

    overview = await _overview(client, admin_user)
    assert overview["treasury"] == 50000
    assert overview["buyer_wallets_total"] == 50000
    assert overview["total_topped_up"] == 50000
    assert overview["is_balanced"] is True


async def test_topup_sync_on_return_and_failed_topup(
    client: AsyncClient, buyer_user: User, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _settings(client, admin_user)
    _stub_initiate(monkeypatch)
    headers = auth_headers(buyer_user)
    first = (await client.post("/ndjouribank/topups", json={"amount": 20000}, headers=headers)).json()["topup"]
    second = (await client.post("/ndjouribank/topups", json={"amount": 30000}, headers=headers)).json()["topup"]

    _stub_djomy_status(monkeypatch, status="SUCCESS")
    synced = await client.post(f"/ndjouribank/topups/{first['id']}/sync", headers=headers)
    assert synced.json()["status"] == "paid"

    await _webhook(client, monkeypatch, second["id"], "payment.failed", "FAILED")
    # Un succès arrivé après un échec ne crédite rien.
    await _webhook(client, monkeypatch, second["id"], "payment.success", "SUCCESS")
    assert await _balance(client, buyer_user) == 20000


async def test_topup_limits(
    client: AsyncClient, buyer_user: User, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _settings(client, admin_user, wallet_max_balance=60000)
    _stub_initiate(monkeypatch)
    headers = auth_headers(buyer_user)
    too_small = await client.post("/ndjouribank/topups", json={"amount": 1000}, headers=headers)
    assert too_small.status_code == 409
    await _top_up(client, buyer_user, monkeypatch, 50000)
    over_cap = await client.post("/ndjouribank/topups", json={"amount": 20000}, headers=headers)
    assert over_cap.status_code == 409
    assert "10000" in over_cap.json()["detail"]


async def test_checkout_with_insufficient_balance_is_refused(
    client: AsyncClient, buyer_user: User, admin_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _settings(client, admin_user)
    await _top_up(client, buyer_user, monkeypatch, 100000)
    await _add_to_cart(client, buyer_user, product)
    response = await client.post("/orders/checkout", json=WALLET_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    assert response.status_code == 409
    assert await _balance(client, buyer_user) == 100000
    assert (await client.get("/orders", headers=auth_headers(buyer_user))).json() == []


async def test_pay_with_wallet_then_delivery_splits_the_money(
    client: AsyncClient,
    buyer_user: User,
    admin_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _settings(client, admin_user)
    await _top_up(client, buyer_user, monkeypatch, 1_000_000)
    await _add_to_cart(client, buyer_user, product)
    response = await client.post("/orders/checkout", json=WALLET_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["payment_method"] == "wallet"
    assert order["payment_status"] == "paid"
    assert order["payment_redirect_url"] is None
    assert await _balance(client, buyer_user) == 1_000_000 - order["total"]
    assert (await _overview(client, admin_user))["escrow"] == order["total"]

    sub_order_id = order["sub_orders"][0]["id"]
    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for status in ("confirmed", "preparing", "shipped"):
        await client.patch(f"/orders/sub-orders/{sub_order_id}/status", json={"status": status}, headers=vendor_headers)
    delivered = await scan_handoff(client, courier_user, sub_order_id)
    assert delivered.status_code == 200, delivered.text

    overview = await _overview(client, admin_user)
    assert overview["escrow"] == 0
    assert overview["beneficiaries_total"] > 0
    assert overview["is_balanced"] is True
    # Le paiement avec le solde n'est pas un nouvel encaissement Djomy.
    assert overview["total_captured"] == 0
    assert overview["treasury"] == 1_000_000


async def test_cancelled_wallet_order_is_refunded_on_the_balance(
    client: AsyncClient, buyer_user: User, admin_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _settings(client, admin_user)
    await _top_up(client, buyer_user, monkeypatch, 1_000_000)
    await _add_to_cart(client, buyer_user, product)
    order = (
        await client.post("/orders/checkout", json=WALLET_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    ).json()

    # Recharges fermées entre-temps : un paiement fait avec le solde revient quand même sur le solde.
    await _settings(client, admin_user, buyer_wallet_enabled=False)
    cancelled = await client.post(f"/orders/{order['id']}/cancel", headers=auth_headers(buyer_user))
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["payment_status"] == "refunded"
    assert body["wallet_refunded_amount"] == order["total"]
    assert await _balance(client, buyer_user) == 1_000_000
    assert (await _overview(client, admin_user))["is_balanced"] is True


async def test_vendor_cancelling_a_wallet_sub_order_refunds_the_balance(
    client: AsyncClient,
    buyer_user: User,
    admin_user: User,
    vendor_user: User,
    product: Product,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _settings(client, admin_user)
    await _top_up(client, buyer_user, monkeypatch, 1_000_000)
    await _add_to_cart(client, buyer_user, product)
    order = (
        await client.post("/orders/checkout", json=WALLET_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    ).json()
    sub_order_id = order["sub_orders"][0]["id"]
    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status", json={"status": "cancelled"}, headers=auth_headers(vendor_user)
    )
    assert response.status_code == 200, response.text

    assert await _balance(client, buyer_user) == 1_000_000
    detail = (await client.get(f"/orders/{order['id']}", headers=auth_headers(buyer_user))).json()
    assert detail["wallet_refunded_amount"] == order["total"]
    assert detail["payment_status"] == "refunded"


async def test_online_order_can_be_refunded_on_the_balance(
    client: AsyncClient, buyer_user: User, admin_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _settings(client, admin_user)
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)

    async def no_payout(**kwargs):
        raise AssertionError("aucun versement Djomy attendu")

    monkeypatch.setattr("app.payments.djomy_client.create_refund_payout", no_payout)
    response = await client.post(
        f"/orders/{order_id}/cancel", json={"refund_to": "wallet"}, headers=auth_headers(buyer_user)
    )
    assert response.status_code == 200, response.text
    assert response.json()["payment_status"] == "refunded"
    total = response.json()["total"]
    assert await _balance(client, buyer_user) == total
    overview = await _overview(client, admin_user)
    assert overview["treasury"] == total
    assert overview["buyer_wallets_total"] == total
    assert overview["is_balanced"] is True


async def test_online_refund_stays_on_djomy_when_wallet_is_closed(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    _stub_djomy_status(monkeypatch)
    _stub_djomy_payout(monkeypatch, item_id="refund-1")
    response = await client.post(
        f"/orders/{order_id}/cancel", json={"refund_to": "wallet"}, headers=auth_headers(buyer_user)
    )
    assert response.status_code == 200, response.text
    assert response.json()["payment_status"] == "refund_pending"
    assert await _balance(client, buyer_user) == 0


async def test_buyer_balance_is_not_withdrawable(
    client: AsyncClient, buyer_user: User, admin_user: User, vendor: Vendor, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _settings(client, admin_user)
    await _top_up(client, buyer_user, monkeypatch, 50000)
    assert (await client.get("/wallets/mine", headers=auth_headers(buyer_user))).json() == []
    [buyer_wallet] = [
        w for w in (await client.get("/admin/finance/wallets", headers=auth_headers(admin_user))).json()
        if w["kind"] == "buyer"
    ]
    response = await client.post(
        f"/wallets/{buyer_wallet['id']}/withdrawals", json={"amount": 20000}, headers=auth_headers(buyer_user)
    )
    assert response.status_code == 404
