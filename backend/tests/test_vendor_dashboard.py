"""Tests for the vendor dashboard: order counts, delivered revenue/commission, low stock."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers, scan_handoff

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


async def _checkout(client: AsyncClient, buyer: User, product: Product, quantity: int = 1) -> dict:
    await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": quantity}, headers=auth_headers(buyer)
    )
    response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer))
    return response.json()


async def _advance_to(
    client: AsyncClient, vendor: User, sub_order_id: str, target: str, courier: Courier, courier_user: User
) -> None:
    # "shipped" exige un livreur assigné — voir
    # app/orders/service.py::update_sub_order_status. Assigné inconditionnellement
    # ici : sans effet sur les statuts n'atteignant pas encore "shipped".
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor),
    )
    for status in ["confirmed", "preparing", "shipped"]:
        await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": status}, headers=auth_headers(vendor)
        )
        if status == target:
            return
    # La remise finale ("delivered") revient au livreur, pas au vendeur.
    await scan_handoff(client, courier_user, sub_order_id)


async def test_dashboard_requires_vendor_registration(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/vendors/me/dashboard", headers=auth_headers(buyer_user))

    assert response.status_code == 404


async def test_dashboard_empty_for_new_vendor(client: AsyncClient, vendor_user: User, product: Product) -> None:
    response = await client.get("/vendors/me/dashboard", headers=auth_headers(vendor_user))

    assert response.status_code == 200
    body = response.json()
    assert body["total_orders"] == 0
    assert body["active_product_count"] == 1
    assert body["low_stock_products"] == []


async def test_dashboard_reflects_delivered_order_revenue_and_commission(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    vendor: Vendor,
    product: Product,
    courier: Courier,
    courier_user: User,
) -> None:
    await client.patch(
        f"/admin/vendors/{vendor.id}", json={"commission_rate": 10}, headers=auth_headers(admin_user)
    )

    order = await _checkout(client, buyer_user, product, quantity=2)
    sub_order_id = order["sub_orders"][0]["id"]
    await _advance_to(client, vendor_user, sub_order_id, "delivered", courier, courier_user)

    response = await client.get("/vendors/me/dashboard", headers=auth_headers(vendor_user))
    body = response.json()

    expected_amount = product.price * 2
    assert body["delivered_orders"] == 1
    assert body["active_orders"] == 0
    assert body["revenue_delivered"] == expected_amount
    assert body["commission_due"] == round(expected_amount * 0.10)
    assert body["net_revenue"] == expected_amount - round(expected_amount * 0.10)


async def test_dashboard_counts_active_order_before_delivery(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    order = await _checkout(client, buyer_user, product)
    sub_order_id = order["sub_orders"][0]["id"]
    await _advance_to(client, vendor_user, sub_order_id, "confirmed", courier, courier_user)

    response = await client.get("/vendors/me/dashboard", headers=auth_headers(vendor_user))
    body = response.json()

    assert body["active_orders"] == 1
    assert body["delivered_orders"] == 0
    assert body["revenue_delivered"] == 0


async def test_dashboard_lists_low_stock_products(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    await client.patch(f"/products/{product.id}", json={"stock": 2}, headers=auth_headers(vendor_user))

    response = await client.get("/vendors/me/dashboard", headers=auth_headers(vendor_user))
    body = response.json()

    assert len(body["low_stock_products"]) == 1
    assert body["low_stock_products"][0]["stock"] == 2
    assert body["out_of_stock_products"] == []


async def test_dashboard_separates_out_of_stock_from_low_stock(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    await client.patch(f"/products/{product.id}", json={"stock": 0}, headers=auth_headers(vendor_user))

    response = await client.get("/vendors/me/dashboard", headers=auth_headers(vendor_user))
    body = response.json()

    # Rupture de stock uniquement dans out_of_stock_products — jamais aussi
    # dans low_stock_products (pas de double affichage du même produit).
    assert len(body["out_of_stock_products"]) == 1
    assert body["out_of_stock_products"][0]["stock"] == 0
    assert body["low_stock_products"] == []
