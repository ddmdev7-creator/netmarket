"""Tests for courier reviews: gated on the buyer having actually been
delivered by that courier, one per (courier, buyer), aggregated onto the
courier read + exposed on the buyer's own SubOrderRead."""

from httpx import AsyncClient

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User
from tests.conftest import auth_headers, scan_handoff

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


async def _buy_and_deliver(
    client: AsyncClient, buyer: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> str:
    add_response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer)
    )
    assert add_response.status_code == 201

    checkout_response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer))
    sub_order_id = checkout_response.json()["sub_orders"][0]["id"]

    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200
    delivered_step = await scan_handoff(client, courier_user, sub_order_id)
    assert delivered_step.status_code == 200
    return sub_order_id


async def test_review_requires_a_delivery_by_this_courier(
    client: AsyncClient, buyer_user: User, courier: Courier
) -> None:
    response = await client.post(
        f"/couriers/{courier.id}/reviews", json={"rating": 5}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 403


async def test_buyer_can_review_the_courier_who_delivered_them(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)

    response = await client.post(
        f"/couriers/{courier.id}/reviews", json={"rating": 4, "comment": "Rapide"}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 4
    assert body["comment"] == "Rapide"


async def test_buyer_cannot_review_the_same_courier_twice(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/couriers/{courier.id}/reviews", json={"rating": 5}, headers=auth_headers(buyer_user))

    response = await client.post(f"/couriers/{courier.id}/reviews", json={"rating": 2}, headers=auth_headers(buyer_user))

    assert response.status_code == 409


async def test_courier_rating_out_of_range_is_rejected(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)

    response = await client.post(f"/couriers/{courier.id}/reviews", json={"rating": 0}, headers=auth_headers(buyer_user))

    assert response.status_code == 422


async def test_courier_read_exposes_rating_summary(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    fresh = await client.get("/couriers", headers=auth_headers(buyer_user))
    entry = next(c for c in fresh.json() if c["id"] == str(courier.id))
    assert entry["average_rating"] is None
    assert entry["review_count"] == 0

    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/couriers/{courier.id}/reviews", json={"rating": 4}, headers=auth_headers(buyer_user))

    detail = await client.get("/couriers/me", headers=auth_headers(courier_user))
    assert detail.json()["average_rating"] == 4
    assert detail.json()["review_count"] == 1


async def test_buyer_order_detail_exposes_the_delivering_courier(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    sub_order_id = await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)

    orders = await client.get("/orders", headers=auth_headers(buyer_user))
    order = next(o for o in orders.json() if any(so["id"] == sub_order_id for so in o["sub_orders"]))
    sub_order = next(so for so in order["sub_orders"] if so["id"] == sub_order_id)

    assert sub_order["courier_id"] == str(courier.id)
    assert sub_order["courier_status"] == "approved"
