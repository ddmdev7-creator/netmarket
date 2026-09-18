"""Tests for the admin dashboard: platform-wide stats and global order visibility."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Product
from app.couriers.models import Courier
from app.users.models import User, UserRole
from tests.conftest import auth_headers, make_user, make_vendor

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


async def _checkout(client: AsyncClient, buyer: User, product: Product) -> dict:
    await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer)
    )
    response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer))
    return response.json()


async def _deliver(
    client: AsyncClient, vendor: User, sub_order_id: str, courier: Courier, courier_user: User
) -> None:
    # "shipped" exige un livreur assigné (voir
    # app/orders/service.py::update_sub_order_status) — d'où l'assignation
    # avant de parcourir les statuts. La remise finale ("delivered") revient
    # au livreur, pas au vendeur (même endroit du backend).
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor),
    )
    for status in ["confirmed", "preparing", "shipped"]:
        await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": status}, headers=auth_headers(vendor)
        )
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status", json={"status": "delivered"}, headers=auth_headers(courier_user)
    )


async def test_stats_requires_admin(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/stats", headers=auth_headers(buyer_user))

    assert response.status_code == 403


async def test_list_orders_requires_admin(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/orders", headers=auth_headers(buyer_user))

    assert response.status_code == 403


async def test_stats_reflect_delivered_and_cancelled_orders(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    category: Category,
    courier: Courier,
    courier_user: User,
) -> None:
    _, other_vendor = await make_vendor(db_session, phone="+224620002222", shop_name="Deuxième Boutique")
    other_product = Product(vendor_id=other_vendor.id, category_id=category.id, name="Casque", price=200000, stock=5)
    db_session.add(other_product)
    await db_session.flush()

    delivered_order = await _checkout(client, buyer_user, product)
    await _deliver(client, vendor_user, delivered_order["sub_orders"][0]["id"], courier, courier_user)

    cancelled_order = await _checkout(client, buyer_user, other_product)
    await client.post(f"/orders/{cancelled_order['id']}/cancel", headers=auth_headers(buyer_user))

    response = await client.get("/admin/stats", headers=auth_headers(admin_user))
    assert response.status_code == 200
    stats = response.json()

    assert stats["total_vendors"] == 2
    assert stats["approved_vendors"] == 2
    assert stats["total_orders"] == 2
    assert stats["orders_by_status"]["delivered"] == 1
    assert stats["orders_by_status"]["cancelled"] == 1
    assert stats["total_sales"] == product.price
    assert any(p["product_name"] == product.name for p in stats["top_products"])
    assert any(v["shop_name"] == "Boutique Test" for v in stats["top_vendors"])


async def test_admin_can_list_all_orders_across_buyers(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, buyer_user: User, product: Product
) -> None:
    other_buyer = await make_user(db_session, phone="+224620001111", role=UserRole.BUYER)

    order_1 = await _checkout(client, buyer_user, product)
    order_2 = await _checkout(client, other_buyer, product)

    response = await client.get("/admin/orders", headers=auth_headers(admin_user))

    assert response.status_code == 200
    body = response.json()
    order_ids = {item["id"] for item in body["items"]}
    assert {order_1["id"], order_2["id"]}.issubset(order_ids)


async def test_admin_order_list_includes_product_images(
    client: AsyncClient, admin_user: User, buyer_user: User, product: Product
) -> None:
    product.images = ["products/casque.jpg"]
    order = await _checkout(client, buyer_user, product)

    response = await client.get("/admin/orders", headers=auth_headers(admin_user))

    assert response.status_code == 200
    listed = next(o for o in response.json()["items"] if o["id"] == order["id"])
    assert listed["sub_orders"][0]["items"][0]["product_image"] == "products/casque.jpg"


async def test_admin_order_detail_includes_buyer_vendor_and_courier_info(
    client: AsyncClient,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
) -> None:
    product.images = ["products/casque.jpg"]
    order = await _checkout(client, buyer_user, product)
    await _deliver(client, vendor_user, order["sub_orders"][0]["id"], courier, courier_user)

    response = await client.get(f"/admin/orders/{order['id']}", headers=auth_headers(admin_user))

    assert response.status_code == 200
    body = response.json()
    assert body["buyer_phone"] == buyer_user.phone
    sub_order = body["sub_orders"][0]
    assert sub_order["vendor_owner_phone"] == vendor_user.phone
    assert sub_order["courier_phone"] == courier_user.phone
    assert sub_order["items"][0]["product_image"] == "products/casque.jpg"


async def test_admin_order_detail_404_for_unknown_order(client: AsyncClient, admin_user: User) -> None:
    response = await client.get(
        "/admin/orders/00000000-0000-0000-0000-000000000000", headers=auth_headers(admin_user)
    )

    assert response.status_code == 404


async def test_admin_order_detail_requires_admin(client: AsyncClient, buyer_user: User, product: Product) -> None:
    order = await _checkout(client, buyer_user, product)

    response = await client.get(f"/admin/orders/{order['id']}", headers=auth_headers(buyer_user))

    assert response.status_code == 403
