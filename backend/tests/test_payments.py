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


def _payout_webhook_payload(event_type: str, payout_id: str, status: str) -> bytes:
    return json.dumps(
        {
            "message": "Statut du transfert",
            "eventType": event_type,
            "eventId": "evt-2",
            "data": {
                "payout": {
                    "payoutId": payout_id,
                    "reference": "A1B2C3",
                    "orderReference": "D4E5F6",
                    "status": status,
                    "amount": 500000,
                    "fees": 3000,
                    "currency": "GNF",
                    "provider": "OM",
                    "destinationAccountNumber": "00224623707722",
                    "beneficiaryName": "Client netmarket",
                    "createdAt": "2026-08-10T10:00:00.000Z",
                }
            },
            "timestamp": "2026-08-10T10:01:00.000Z",
        }
    ).encode()


def _stub_djomy_status(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    data = {
        "transactionId": "txn-123",
        "status": "SUCCESS",
        "paidAmount": 500000,
        "payerIdentifier": "00224623707722",
        "paymentMethod": "OM",
        "merchantPaymentReference": "order-ref",
        "currency": "GNF",
        "createdAt": "2026-08-10T10:00:00.000Z",
    }
    data.update(overrides)

    async def fake_status(transaction_id: str) -> dict:
        return data

    monkeypatch.setattr("app.payments.djomy_client.get_payment_status", fake_status)


def _stub_djomy_payout(monkeypatch: pytest.MonkeyPatch, item_id: str = "payout-item-1") -> None:
    async def fake_payout(**kwargs) -> str:
        return item_id

    monkeypatch.setattr("app.payments.djomy_client.create_refund_payout", fake_payout)


async def _checkout_and_pay_online(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Checkout with online payment, then simulate the payment.success
    webhook — returns the order id, with payment_status already "paid"."""
    _stub_djomy_initiate(monkeypatch)
    await _add_to_cart(client, buyer_user, product)
    checkout = await client.post("/orders/checkout", json=ONLINE_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    order_id = checkout.json()["id"]

    body = _webhook_payload(order_id, "payment.success", "SUCCESS")
    signature = _sign_webhook(monkeypatch, body)
    await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )
    return order_id


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


async def test_admin_manages_refund_delay_setting(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    default = await client.get("/admin/payment-settings", headers=headers)
    assert default.status_code == 200
    assert default.json()["refund_delay_hours"] == 48

    updated = await client.patch("/admin/payment-settings", json={"refund_delay_hours": 72}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["refund_delay_hours"] == 72

    again = await client.get("/admin/payment-settings", headers=headers)
    assert again.json()["refund_delay_hours"] == 72


async def test_refund_delay_setting_is_admin_only(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/payment-settings", headers=auth_headers(buyer_user))
    assert response.status_code == 403


async def test_cancel_online_paid_order_initiates_a_refund(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    _stub_djomy_status(monkeypatch)
    _stub_djomy_payout(monkeypatch, item_id="payout-item-1")

    cancel_response = await client.post(f"/orders/{order_id}/cancel", headers=auth_headers(buyer_user))

    assert cancel_response.status_code == 200
    body = cancel_response.json()
    assert body["status"] == "cancelled"
    assert body["payment_status"] == "refund_pending"
    assert body["refund_delay_hours"] == 48

    # La commande reste visible comme "en remboursement" tant que le webhook
    # payout.* n'est pas arrivé (voir test suivant).
    order_response = await client.get(f"/orders/{order_id}", headers=auth_headers(buyer_user))
    assert order_response.json()["payment_status"] == "refund_pending"


async def test_payout_webhook_marks_the_refund_settled(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    _stub_djomy_status(monkeypatch)
    _stub_djomy_payout(monkeypatch, item_id="payout-item-1")
    await client.post(f"/orders/{order_id}/cancel", headers=auth_headers(buyer_user))

    body = _payout_webhook_payload("payout.success", "payout-item-1", "SUCCESS")
    signature = _sign_webhook(monkeypatch, body)
    webhook_response = await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )
    assert webhook_response.status_code == 200

    order_response = await client.get(f"/orders/{order_id}", headers=auth_headers(buyer_user))
    assert order_response.json()["payment_status"] == "refunded"
    # Réglée : plus besoin d'afficher un délai estimé.
    assert order_response.json()["refund_delay_hours"] is None


async def test_payout_webhook_marks_the_refund_failed(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    _stub_djomy_status(monkeypatch)
    _stub_djomy_payout(monkeypatch, item_id="payout-item-1")
    await client.post(f"/orders/{order_id}/cancel", headers=auth_headers(buyer_user))

    body = _payout_webhook_payload("payout.failed", "payout-item-1", "REJECTED")
    signature = _sign_webhook(monkeypatch, body)
    await client.post(
        "/payments/webhooks/djomy",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )

    order_response = await client.get(f"/orders/{order_id}", headers=auth_headers(buyer_user))
    assert order_response.json()["payment_status"] == "refund_failed"


async def test_cancel_is_aborted_when_djomy_refund_details_are_incomplete(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si Djomy ne renvoie ni payerIdentifier ni paymentMethod (ne devrait pas
    arriver pour un paiement SUCCESS, mais on ne fait pas confiance
    aveuglément), toute la commande doit rester intacte plutôt que d'annuler
    sans que l'argent ne revienne."""
    order_id = await _checkout_and_pay_online(client, buyer_user, product, monkeypatch)
    _stub_djomy_status(monkeypatch, payerIdentifier=None)

    cancel_response = await client.post(f"/orders/{order_id}/cancel", headers=auth_headers(buyer_user))
    assert cancel_response.status_code == 409

    order_response = await client.get(f"/orders/{order_id}", headers=auth_headers(buyer_user))
    assert order_response.json()["status"] == "pending"
    assert order_response.json()["payment_status"] == "paid"


async def test_cancel_online_order_still_pending_does_not_attempt_a_refund(
    client: AsyncClient, buyer_user: User, product: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un paiement en ligne jamais confirmé (toujours PENDING) suit le même
    chemin que cash on delivery — rien à rembourser."""
    _stub_djomy_initiate(monkeypatch)
    await _add_to_cart(client, buyer_user, product)
    checkout = await client.post("/orders/checkout", json=ONLINE_CHECKOUT_PAYLOAD, headers=auth_headers(buyer_user))
    order_id = checkout.json()["id"]

    cancel_response = await client.post(f"/orders/{order_id}/cancel", headers=auth_headers(buyer_user))

    assert cancel_response.status_code == 200
    assert cancel_response.json()["payment_status"] == "cancelled"
