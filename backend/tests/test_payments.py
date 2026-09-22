"""Tests for the payments module: created at checkout, settled on delivery/cancellation."""

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User
from tests.conftest import auth_headers

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}
ONLINE_CHECKOUT_PAYLOAD = {
    "delivery_address": "Kaloum, près du marché",
    "payment_method": "online",
    "payer_phone": "00224623707722",
}


def _stub_djomy_initiate(monkeypatch: pytest.MonkeyPatch, transaction_id: str = "txn-123") -> None:
    async def fake_initiate(**kwargs) -> tuple[str, str]:
        return transaction_id, f"https://sandbox.djomy.africa/c/{transaction_id}"

    monkeypatch.setattr("app.payments.djomy_client.initiate_gateway_payment", fake_initiate)


def _sign_webhook(monkeypatch: pytest.MonkeyPatch, body: bytes, secret: str = "test-webhook-secret") -> str:
    monkeypatch.setattr("app.payments.djomy_client.settings.djomy_client_secret", secret)
    return f"v1:{hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}"


def _webhook_payload(order_id: str, event_type: str, status: str) -> bytes:
    return json.dumps(
        {
            "message": "Statut du paiement",
            "eventType": event_type,
            "eventId": "evt-1",
            "data": {
                "payment": {
                    "transactionId": "txn-123",
                    "status": status,
                    "paidAmount": 500000,
                    "paymentMethod": "OM",
                    "merchantPaymentReference": order_id,
                    "currency": "GNF",
                    "createdAt": "2026-08-10T10:00:00.000Z",
                }
            },
            "timestamp": "2026-08-10T10:01:00.000Z",
        }
    ).encode()


async def _add_to_cart(client: AsyncClient, user: User, product: Product, quantity: int = 1) -> None:
    response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": quantity}, headers=auth_headers(user)
    )
    assert response.status_code == 201


async def test_checkout_creates_pending_cash_on_delivery_payment(
    client: AsyncClient, buyer_user: User, product: Product
) -> None:
    await _add_to_cart(client, buyer_user, product)
    response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))

    order = response.json()
    assert order["payment_method"] == "cash_on_delivery"
    assert order["payment_status"] == "pending"


async def test_payment_marked_paid_once_order_fully_delivered(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, product: Product, courier: Courier
) -> None:
    await _add_to_cart(client, buyer_user, product)
    checkout_response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    order = checkout_response.json()
    sub_order_id = order["sub_orders"][0]["id"]
    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )

    for target_status in ("confirmed", "preparing", "shipped"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200
    # La remise finale revient au livreur, pas au vendeur.
    delivered_step = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(courier_user),
    )
    assert delivered_step.status_code == 200

    order_response = await client.get(f"/orders/{order['id']}", headers=auth_headers(buyer_user))
    assert order_response.json()["payment_status"] == "paid"


async def test_payment_marked_cancelled_when_buyer_cancels_order(
    client: AsyncClient, buyer_user: User, product: Product
) -> None:
    await _add_to_cart(client, buyer_user, product)
    checkout_response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    order_id = checkout_response.json()["id"]

    cancel_response = await client.post(f"/orders/{order_id}/cancel", headers=auth_headers(buyer_user))

    assert cancel_response.json()["payment_status"] == "cancelled"


async def test_order_list_includes_payment_status_for_each_order(
    client: AsyncClient, buyer_user: User, product: Product
) -> None:
    await _add_to_cart(client, buyer_user, product)
    await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))

    list_response = await client.get("/orders", headers=auth_headers(buyer_user))

    assert list_response.status_code == 200
    assert all(order["payment_status"] == "pending" for order in list_response.json())


async def test_online_checkout_returns_a_redirect_url(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_djomy_initiate(monkeypatch)
    await _add_to_cart(client, buyer_user, product)

    response = await client.post("/orders/checkout", json=ONLINE_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))

    order = response.json()
    assert order["payment_method"] == "online"
    assert order["payment_status"] == "pending"
    assert order["payment_redirect_url"] == "https://sandbox.djomy.africa/c/txn-123"


async def test_djomy_webhook_marks_payment_paid(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_djomy_initiate(monkeypatch)
    await _add_to_cart(client, buyer_user, product)
    checkout = await client.post("/orders/checkout", json=ONLINE_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    order_id = checkout.json()["id"]

    body = _webhook_payload(order_id, "payment.success", "SUCCESS")
    signature = _sign_webhook(monkeypatch, body)
    webhook_response = await client.post(
        "/payments/webhooks/djomy", content=body, headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"}
    )
    assert webhook_response.status_code == 200

    order_response = await client.get(f"/orders/{order_id}", headers=auth_headers(buyer_user))
    assert order_response.json()["payment_status"] == "paid"


async def test_djomy_webhook_rejects_an_invalid_signature(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_djomy_initiate(monkeypatch)
    await _add_to_cart(client, buyer_user, product)
    checkout = await client.post("/orders/checkout", json=ONLINE_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    order_id = checkout.json()["id"]

    body = _webhook_payload(order_id, "payment.success", "SUCCESS")
    _sign_webhook(monkeypatch, body)  # configure le secret, on ignore la signature retournée
    webhook_response = await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": "v1:not-the-right-signature", "Content-Type": "application/json"},
    )
    assert webhook_response.status_code == 400

    order_response = await client.get(f"/orders/{order_id}", headers=auth_headers(buyer_user))
    assert order_response.json()["payment_status"] == "pending"


async def test_delivery_does_not_mark_an_online_payment_paid(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    product: Product,
    courier: Courier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contrairement au paiement à la livraison, un colis livré ne doit
    jamais, à lui seul, faire passer un paiement en ligne à "paid" — seul le
    webhook Djomy (ou la synchronisation de repli) en a l'autorité."""
    _stub_djomy_initiate(monkeypatch)
    await _add_to_cart(client, buyer_user, product)
    checkout = await client.post("/orders/checkout", json=ONLINE_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    order = checkout.json()
    sub_order_id = order["sub_orders"][0]["id"]
    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(courier_user),
    )

    order_response = await client.get(f"/orders/{order['id']}", headers=auth_headers(buyer_user))
    assert order_response.json()["payment_status"] == "pending"
