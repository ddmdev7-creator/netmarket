"""Tests for pickup point reviews: gated on the buyer having actually
received a delivered order routed through that point, one per (point,
buyer), aggregated onto the pickup point read + exposed on OrderRead."""

from httpx import AsyncClient

from app.couriers.models import Courier
from app.pickup_point_managers.models import PickupPointManager
from app.pickup_points.models import PickupPoint
from app.users.models import User
from tests.conftest import auth_headers, scan_handoff


def _pickup_payload(point: PickupPoint) -> dict:
    return {
        "delivery_address": f"{point.name} — {point.zone}",
        "delivery_type": "pickup_point",
        "pickup_point_id": str(point.id),
        "payment_method": "cash_on_delivery",
    }


async def _checkout(client: AsyncClient, buyer: User, product, payload: dict) -> str:
    await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer))
    response = await client.post("/orders/checkout", json=payload, headers=auth_headers(buyer))
    assert response.status_code == 201, response.text
    return response.json()["sub_orders"][0]["id"]


async def _buy_and_deliver_via_pickup_point(
    client: AsyncClient,
    buyer: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    product,
    point: PickupPoint,
) -> None:
    sub_order_id = await _checkout(client, buyer, product, _pickup_payload(point))
    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200, step.text

    step_a = await scan_handoff(client, manager_user, sub_order_id)
    assert step_a.status_code == 200

    step_b = await scan_handoff(client, manager_user, sub_order_id)
    assert step_b.status_code == 200
    assert step_b.json()["status"] == "delivered"


async def test_review_requires_a_delivery_via_this_point(
    client: AsyncClient, buyer_user: User, pickup_point: PickupPoint
) -> None:
    response = await client.post(
        f"/pickup-points/{pickup_point.id}/reviews", json={"rating": 5}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 403


async def test_buyer_can_review_a_pickup_point_they_used(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    manager: PickupPointManager,
    product,
    pickup_point: PickupPoint,
) -> None:
    await _buy_and_deliver_via_pickup_point(
        client, buyer_user, vendor_user, courier_user, courier, manager_user, product, pickup_point
    )

    response = await client.post(
        f"/pickup-points/{pickup_point.id}/reviews",
        json={"rating": 5, "comment": "Bien situé"},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 201
    assert response.json()["rating"] == 5


async def test_buyer_cannot_review_the_same_pickup_point_twice(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    manager: PickupPointManager,
    product,
    pickup_point: PickupPoint,
) -> None:
    await _buy_and_deliver_via_pickup_point(
        client, buyer_user, vendor_user, courier_user, courier, manager_user, product, pickup_point
    )
    await client.post(
        f"/pickup-points/{pickup_point.id}/reviews", json={"rating": 5}, headers=auth_headers(buyer_user)
    )

    response = await client.post(
        f"/pickup-points/{pickup_point.id}/reviews", json={"rating": 3}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 409


async def test_pickup_point_read_exposes_rating_summary(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    manager: PickupPointManager,
    product,
    pickup_point: PickupPoint,
) -> None:
    fresh = await client.get("/pickup-points")
    entry = next(p for p in fresh.json() if p["id"] == str(pickup_point.id))
    assert entry["average_rating"] is None
    assert entry["review_count"] == 0

    await _buy_and_deliver_via_pickup_point(
        client, buyer_user, vendor_user, courier_user, courier, manager_user, product, pickup_point
    )
    await client.post(
        f"/pickup-points/{pickup_point.id}/reviews", json={"rating": 3}, headers=auth_headers(buyer_user)
    )

    detail = await client.get("/pickup-points")
    updated = next(p for p in detail.json() if p["id"] == str(pickup_point.id))
    assert updated["average_rating"] == 3
    assert updated["review_count"] == 1


async def test_buyer_order_exposes_the_pickup_point_used(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    manager: PickupPointManager,
    product,
    pickup_point: PickupPoint,
) -> None:
    await _buy_and_deliver_via_pickup_point(
        client, buyer_user, vendor_user, courier_user, courier, manager_user, product, pickup_point
    )

    orders = await client.get("/orders", headers=auth_headers(buyer_user))
    order = next(o for o in orders.json() if o["pickup_point_id"] == str(pickup_point.id))

    assert order["pickup_point_name"] == pickup_point.name
