"""Tests for proximity-based courier dispatch: sequential offer to the
nearest online courier, escalating to the next if declined/unanswered.

The actual timeout-driven escalation (_run_dispatch's background task) opens
its own DB session outside the test's transaction — by design (see
app/orders/service.py), so it can't see this test's uncommitted rows. That
loop is exercised live on the dev server instead; here we test the pure
escalation logic (_offer_next) directly against the test session, plus
everything reachable through the request/response cycle (start_dispatch's
validation and its synchronous first-offer, accept/decline's authorization
and effects).
"""

from httpx import AsyncClient

from app.couriers.models import Courier, CourierStatus, VehicleType
from app.orders import service as orders_service
from app.orders.models import SubOrder
from app.users.models import User, UserRole
from app.vendors.models import Vendor
from tests.conftest import auth_headers, make_user

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}

# Conakry-ish coordinates, spread out enough to give clearly different
# haversine distances.
VENDOR_LAT, VENDOR_LNG = 9.6412, -13.5784
NEAR_LAT, NEAR_LNG = 9.6420, -13.5790  # ~0.1 km
FAR_LAT, FAR_LNG = 9.7500, -13.7000  # ~15 km


async def _checkout(client: AsyncClient, buyer: User, product) -> str:
    await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer)
    )
    response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer))
    return response.json()["sub_orders"][0]["id"]


async def _set_vendor_location(db_session, vendor: Vendor, lat: float, lng: float) -> None:
    vendor.latitude = lat
    vendor.longitude = lng
    await db_session.flush()


async def _make_online_courier(db_session, *, phone: str, lat: float, lng: float, vehicle_type=VehicleType.MOTO) -> Courier:
    user = await make_user(db_session, phone=phone, role=UserRole.COURIER)
    courier = Courier(
        user_id=user.id,
        vehicle_type=vehicle_type,
        status=CourierStatus.APPROVED,
        is_online=True,
        latitude=lat,
        longitude=lng,
    )
    db_session.add(courier)
    await db_session.flush()
    return courier


async def test_dispatch_without_vendor_location_is_rejected(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user)
    )

    assert response.status_code == 409


async def test_dispatch_without_online_courier_is_rejected(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user)
    )

    assert response.status_code == 409


async def test_dispatch_offers_nearest_courier_first(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    far = await _make_online_courier(db_session, phone="+224621000001", lat=FAR_LAT, lng=FAR_LNG)
    near = await _make_online_courier(db_session, phone="+224621000002", lat=NEAR_LAT, lng=NEAR_LNG)
    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user)
    )

    assert response.status_code == 200
    assert response.json()["dispatch_offered_courier_id"] == str(near.id)

    sub_order = await orders_service.repository.get_sub_order_by_id(db_session, sub_order_id)
    assert sub_order.dispatch_queue == [far.id]


async def test_dispatch_filters_by_vehicle_type(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    await _make_online_courier(db_session, phone="+224621000003", lat=NEAR_LAT, lng=NEAR_LNG, vehicle_type=VehicleType.MOTO)
    taxi = await _make_online_courier(
        db_session, phone="+224621000004", lat=FAR_LAT, lng=FAR_LNG, vehicle_type=VehicleType.TAXI
    )
    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/dispatch",
        json={"vehicle_type": "taxi"},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 200
    assert response.json()["dispatch_offered_courier_id"] == str(taxi.id)


async def test_dispatch_ignores_offline_couriers(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    offline_user = await make_user(db_session, phone="+224621000005", role=UserRole.COURIER)
    db_session.add(
        Courier(
            user_id=offline_user.id,
            vehicle_type=VehicleType.MOTO,
            status=CourierStatus.APPROVED,
            is_online=False,
            latitude=NEAR_LAT,
            longitude=NEAR_LNG,
        )
    )
    await db_session.flush()
    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user)
    )

    assert response.status_code == 409


async def test_non_offered_courier_cannot_accept(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    offered = await _make_online_courier(db_session, phone="+224621000006", lat=NEAR_LAT, lng=NEAR_LNG)
    other = await _make_online_courier(db_session, phone="+224621000007", lat=FAR_LAT, lng=FAR_LNG)
    sub_order_id = await _checkout(client, buyer_user, product)
    await client.post(f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user))

    other_user = await orders_service.user_repository.get_by_id(db_session, other.user_id)
    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/accept-delivery", headers=auth_headers(other_user)
    )

    assert response.status_code == 403


async def test_offered_courier_can_accept(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    near = await _make_online_courier(db_session, phone="+224621000008", lat=NEAR_LAT, lng=NEAR_LNG)
    sub_order_id = await _checkout(client, buyer_user, product)
    await client.post(f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user))

    near_user = await orders_service.user_repository.get_by_id(db_session, near.user_id)
    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/accept-delivery", headers=auth_headers(near_user)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["courier_id"] == str(near.id)
    assert body["dispatch_offered_courier_id"] is None

    notifications = await client.get("/notifications", headers=auth_headers(vendor_user))
    assert any(n["type"] == "delivery_request_accepted" for n in notifications.json()["items"])


async def test_cannot_accept_already_assigned_delivery(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    near = await _make_online_courier(db_session, phone="+224621000009", lat=NEAR_LAT, lng=NEAR_LNG)
    sub_order_id = await _checkout(client, buyer_user, product)
    await client.post(f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user))
    near_user = await orders_service.user_repository.get_by_id(db_session, near.user_id)
    await client.post(f"/orders/sub-orders/{sub_order_id}/accept-delivery", headers=auth_headers(near_user))

    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/accept-delivery", headers=auth_headers(near_user)
    )

    assert response.status_code == 409


async def test_non_offered_courier_cannot_decline(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    await _make_online_courier(db_session, phone="+224621000010", lat=NEAR_LAT, lng=NEAR_LNG)
    other = await _make_online_courier(db_session, phone="+224621000011", lat=FAR_LAT, lng=FAR_LNG)
    sub_order_id = await _checkout(client, buyer_user, product)
    await client.post(f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user))

    other_user = await orders_service.user_repository.get_by_id(db_session, other.user_id)
    response = await client.post(
        f"/orders/sub-orders/{sub_order_id}/decline-delivery", headers=auth_headers(other_user)
    )

    assert response.status_code == 403


async def test_offer_next_skips_offline_and_exhausts_queue(db_session, vendor: Vendor) -> None:
    """Direct unit test of the escalation logic (see module docstring for
    why the background task itself isn't exercised through the API here)."""
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    gone_offline = await _make_online_courier(db_session, phone="+224621000012", lat=NEAR_LAT, lng=NEAR_LNG)
    gone_offline.is_online = False
    still_online = await _make_online_courier(db_session, phone="+224621000013", lat=FAR_LAT, lng=FAR_LNG)
    await db_session.flush()

    sub_order = SubOrder(
        order_id=None,
        vendor_id=vendor.id,
        amount=1000,
        commission=0,
        shop_name="Boutique Test",
        dispatch_queue=[gone_offline.id, still_online.id],
    )
    # order_id is required at the DB level but this unit test never commits —
    # only exercises _offer_next's in-memory queue logic against the ORM
    # object directly.
    found = await orders_service._offer_next(db_session, sub_order, VENDOR_LAT, VENDOR_LNG)
    assert found is True
    assert sub_order.dispatch_offered_courier_id == still_online.id
    assert sub_order.dispatch_queue == []

    sub_order.dispatch_offered_courier_id = None
    sub_order.dispatch_queue = []
    found_again = await orders_service._offer_next(db_session, sub_order, VENDOR_LAT, VENDOR_LNG)
    assert found_again is False


async def test_delivery_offer_shows_courier_earning_but_never_the_item_price(
    client: AsyncClient, db_session, monkeypatch, buyer_user: User, vendor_user: User, vendor: Vendor, product
) -> None:
    await _set_vendor_location(db_session, vendor, VENDOR_LAT, VENDOR_LNG)
    near = await _make_online_courier(db_session, phone="+224621000090", lat=NEAR_LAT, lng=NEAR_LNG)
    other = await _make_online_courier(db_session, phone="+224621000091", lat=FAR_LAT, lng=FAR_LNG)
    sub_order_id = await _checkout(client, buyer_user, product)
    sub_order = await orders_service.repository.get_sub_order_by_id(db_session, sub_order_id)
    sub_order.delivery_fee = 20000
    await db_session.flush()
    bodies: list[str] = []

    async def capture(db, *, courier_user_id, sub_order_id, shop_name, courier_earning, distance_km):
        bodies.append(f"{shop_name}|{courier_earning}")

    monkeypatch.setattr(orders_service.notifications_service, "notify_delivery_request", capture)
    await client.post(f"/orders/sub-orders/{sub_order_id}/dispatch", json={}, headers=auth_headers(vendor_user))

    near_user = await db_session.get(User, near.user_id)
    response = await client.get(f"/orders/sub-orders/{sub_order_id}/delivery-offer", headers=auth_headers(near_user))
    assert response.status_code == 200, response.text
    offer = response.json()
    assert offer["courier_earning"] == 16000  # 80 % de 20 000
    assert offer["distance_to_shop_km"] is not None
    assert "amount" not in offer and "total" not in offer
    assert str(product.price) not in response.text
    assert bodies == [f"{sub_order.shop_name}|16000"]

    # Un autre livreur (pas celui sollicité) ne voit rien.
    other_user = await db_session.get(User, other.user_id)
    hidden = await client.get(f"/orders/sub-orders/{sub_order_id}/delivery-offer", headers=auth_headers(other_user))
    assert hidden.status_code == 404
