"""Tests for /admin/deliveries/active: parcels not yet at their destination,
with the shop's position (origin) and the one frozen at checkout (destination)."""

from httpx import AsyncClient

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers, scan_handoff


async def _checkout(client: AsyncClient, buyer: User, product: Product, **destination) -> str:
    await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer))
    response = await client.post(
        "/orders/checkout",
        json={"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery", **destination},
        headers=auth_headers(buyer),
    )
    assert response.status_code == 201
    return response.json()["sub_orders"][0]["id"]


async def test_lists_in_flight_parcels_with_origin_and_destination(
    client: AsyncClient,
    db_session,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    vendor: Vendor,
    product: Product,
    courier: Courier,
) -> None:
    vendor.latitude, vendor.longitude = 9.51, -13.70
    await db_session.flush()
    sub_order_id = await _checkout(client, buyer_user, product, latitude=9.55, longitude=-13.65)
    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    await client.patch(f"/orders/sub-orders/{sub_order_id}/status", json={"status": "confirmed"}, headers=vendor_headers)

    response = await client.get("/admin/deliveries/active", headers=auth_headers(admin_user))

    assert response.status_code == 200
    [entry] = [d for d in response.json() if d["sub_order_id"] == sub_order_id]
    assert entry["status"] == "confirmed"
    assert entry["courier_id"] == str(courier.id)
    assert (entry["origin_latitude"], entry["origin_longitude"]) == (9.51, -13.70)
    assert (entry["destination_latitude"], entry["destination_longitude"]) == (9.55, -13.65)


async def test_pending_parcels_are_not_listed(
    client: AsyncClient, admin_user: User, buyer_user: User, product: Product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.get("/admin/deliveries/active", headers=auth_headers(admin_user))

    assert all(d["sub_order_id"] != sub_order_id for d in response.json())


async def test_pickup_point_destination_is_the_point_position(
    client: AsyncClient,
    db_session,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    pickup_point,
) -> None:
    pickup_point.latitude, pickup_point.longitude = 9.60, -13.60
    await db_session.flush()
    sub_order_id = await _checkout(
        client, buyer_user, product, delivery_type="pickup_point", pickup_point_id=str(pickup_point.id)
    )
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status", json={"status": "confirmed"}, headers=auth_headers(vendor_user)
    )

    response = await client.get("/admin/deliveries/active", headers=auth_headers(admin_user))

    [entry] = [d for d in response.json() if d["sub_order_id"] == sub_order_id]
    assert entry["pickup_point_name"] == "Point Test"
    assert (entry["destination_latitude"], entry["destination_longitude"]) == (9.60, -13.60)


async def test_requires_admin(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/deliveries/active", headers=auth_headers(buyer_user))

    assert response.status_code == 403


async def test_monitor_lists_in_flight_and_delivered_today(
    client: AsyncClient,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
) -> None:
    vendor_headers = auth_headers(vendor_user)
    in_flight = await _checkout(client, buyer_user, product)
    await client.patch(
        f"/orders/sub-orders/{in_flight}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    await client.patch(f"/orders/sub-orders/{in_flight}/status", json={"status": "confirmed"}, headers=vendor_headers)

    delivered = await _checkout(client, buyer_user, product)
    await client.patch(
        f"/orders/sub-orders/{delivered}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for status in ["confirmed", "preparing", "shipped"]:
        await client.patch(f"/orders/sub-orders/{delivered}/status", json={"status": status}, headers=vendor_headers)
    await scan_handoff(client, courier_user, delivered)

    pending = await _checkout(client, buyer_user, product)

    response = await client.get("/admin/deliveries/monitor", headers=auth_headers(admin_user))

    assert response.status_code == 200
    entries = {e["sub_order_id"]: e for e in response.json()["entries"]}
    assert entries[in_flight]["status"] == "confirmed"
    assert entries[in_flight]["courier_phone"] == courier_user.phone
    assert entries[in_flight]["shop_name"] == "Boutique Test"
    assert entries[delivered]["status"] == "delivered"
    assert pending not in entries


async def test_monitor_requires_admin(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/deliveries/monitor", headers=auth_headers(buyer_user))

    assert response.status_code == 403
