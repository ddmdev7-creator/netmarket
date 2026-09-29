"""Moyens de paiement proposés : paiement à la livraison fermé par réglage admin."""

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.payments.models import PaymentSettings
from app.users.models import User
from tests.conftest import auth_headers

COD_CHECKOUT = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


async def test_cash_on_delivery_refused_when_disabled(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, product: Product
) -> None:
    await db_session.execute(update(PaymentSettings).values(cash_on_delivery_enabled=False))
    await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer_user))

    response = await client.post("/orders/checkout", json=COD_CHECKOUT, headers=auth_headers(buyer_user))

    assert response.status_code == 409
    options = (await client.get("/payments/options")).json()
    assert options == {"cash_on_delivery": False, "online": True, "wallet": False}


async def test_admin_toggles_cash_on_delivery(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    body = (await client.patch("/admin/payment-settings", json={"cash_on_delivery_enabled": False}, headers=headers)).json()
    assert body["cash_on_delivery_enabled"] is False and body["refund_delay_hours"] == 48

    body = (await client.patch("/admin/payment-settings", json={"refund_delay_hours": 24}, headers=headers)).json()
    assert body == {"refund_delay_hours": 24, "cash_on_delivery_enabled": False}
