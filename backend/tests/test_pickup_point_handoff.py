"""Tests for the pickup_point two-step handoff: courier drops off at the
point (shipped -> arrived_at_pickup_point), then the pickup point manager
confirms the final handoff to the buyer (arrived_at_pickup_point ->
delivered). home_delivery must keep working exactly as before throughout."""

from httpx import AsyncClient

from app.couriers.models import Courier
from app.pickup_point_managers.models import PickupPointManager
from app.pickup_points.models import PickupPoint
from app.users.models import User, UserRole
from tests.conftest import auth_headers, make_user

HOME_DELIVERY_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


def _pickup_payload(point: PickupPoint) -> dict:
    return {
        "delivery_address": f"{point.name} — {point.zone}",
        "delivery_type": "pickup_point",
        "pickup_point_id": str(point.id),
        "payment_method": "cash_on_delivery",
    }


async def _checkout(client: AsyncClient, buyer: User, product, payload: dict) -> str:
    await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer)
    )
    response = await client.post("/orders/checkout", json=payload, headers=auth_headers(buyer))
    assert response.status_code == 201, response.text
    return response.json()["sub_orders"][0]["id"]


async def _ship_pickup_order(
    client: AsyncClient, buyer: User, vendor_user: User, courier_user: User, courier: Courier, product, point: PickupPoint
) -> str:
    """Checkout a pickup_point order, assign the courier, and advance it
    through confirmed/preparing/shipped — returns the sub-order id."""
    sub_order_id = await _checkout(client, buyer, product, _pickup_payload(point))
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor_user),
    )
    vendor_headers = auth_headers(vendor_user)
    for target_status in ("confirmed", "preparing", "shipped"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200, step.text
    return sub_order_id


async def test_home_delivery_still_ships_directly_to_delivered(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product
) -> None:
    """Regression guard: home_delivery must be entirely unaffected by the
    pickup_point two-step machinery."""
    sub_order_id = await _checkout(client, buyer_user, product, HOME_DELIVERY_PAYLOAD)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor_user),
    )
    vendor_headers = auth_headers(vendor_user)
    for target_status in ("confirmed", "preparing", "shipped"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "delivered"


async def test_pickup_point_courier_cannot_mark_delivered_directly(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product, pickup_point: PickupPoint
) -> None:
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 403


async def test_courier_cannot_confirm_arrival_manually(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product, pickup_point: PickupPoint
) -> None:
    """Only the pickup point manager confirms receipt — the courier's role at
    this stage is limited to showing their drop-off QR, never calling the
    status endpoint themselves (see update_sub_order_status)."""
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "arrived_at_pickup_point"},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 403


async def test_courier_cannot_confirm_arrival_via_own_qr_token(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product, pickup_point: PickupPoint
) -> None:
    """Having a valid drop-off token isn't enough — confirm-delivery still
    authorizes on who's calling it (see confirm_delivery_by_token), and the
    courier submitting their own token is still the courier, not the manager
    meant to scan it."""
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    listing = await client.get("/orders/courier-deliveries", headers=auth_headers(courier_user))
    entry = next(so for so in listing.json() if so["id"] == sub_order_id)
    assert entry["pickup_dropoff_token"] is not None

    response = await client.post(
        "/orders/sub-orders/confirm-delivery",
        json={"token": entry["pickup_dropoff_token"]},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 403


async def test_vendor_cannot_confirm_arrival_at_pickup_point(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product, pickup_point: PickupPoint
) -> None:
    """Only the pickup point manager confirms receipt — never the vendor,
    who no longer has the parcel in hand at this stage (see
    update_sub_order_status's is_owner_vendor guard)."""
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "arrived_at_pickup_point"},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 403


async def test_unassigned_manager_cannot_confirm_delivery(
    client: AsyncClient,
    db_session,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    product,
    pickup_point: PickupPoint,
) -> None:
    other_point = PickupPoint(name="Autre point", zone="Matam")
    db_session.add(other_point)
    await db_session.flush()
    other_manager_user = await make_user(db_session, phone="+224620009995", role=UserRole.PICKUP_POINT_MANAGER)
    other_manager = PickupPointManager(user_id=other_manager_user.id, pickup_point_id=other_point.id)
    db_session.add(other_manager)
    await db_session.flush()

    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "arrived_at_pickup_point"},
        headers=auth_headers(other_manager_user),
    )

    assert response.status_code == 403


async def test_manager_confirms_arrival_then_final_handoff_via_scan(
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
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    # Étape A : le gestionnaire scanne le code de dépôt du livreur.
    courier_listing = await client.get("/orders/courier-deliveries", headers=auth_headers(courier_user))
    dropoff_token = next(so for so in courier_listing.json() if so["id"] == sub_order_id)["pickup_dropoff_token"]

    step_a = await client.post(
        "/orders/sub-orders/confirm-delivery",
        json={"token": dropoff_token},
        headers=auth_headers(manager_user),
    )
    assert step_a.status_code == 200
    assert step_a.json()["status"] == "arrived_at_pickup_point"

    # Étape B : le gestionnaire scanne le QR de l'acheteur.
    order_view = await client.get("/orders", headers=auth_headers(buyer_user))
    order = next(o for o in order_view.json() if any(so["id"] == sub_order_id for so in o["sub_orders"]))
    sub_order = next(so for so in order["sub_orders"] if so["id"] == sub_order_id)
    assert sub_order["delivery_token"] is not None

    step_b = await client.post(
        "/orders/sub-orders/confirm-delivery",
        json={"token": sub_order["delivery_token"]},
        headers=auth_headers(manager_user),
    )
    assert step_b.status_code == 200
    assert step_b.json()["status"] == "delivered"


async def test_manager_cannot_skip_to_delivered_before_arrival(
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
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    # Le gestionnaire est bien autorisé à agir sur cette sous-commande (pas de
    # 403) mais la machine à états lui refuse de sauter l'étape "arrivée au
    # point" (409) — même verdict que pour n'importe quel acteur essayant une
    # transition hors séquence.
    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(manager_user),
    )

    assert response.status_code == 409


async def test_vendor_cannot_ship_without_assigning_a_courier(
    client: AsyncClient, buyer_user: User, vendor_user: User, product, pickup_point: PickupPoint
) -> None:
    """A parcel can't be "on its way" with nobody assigned to carry it — see
    app/orders/service.py::update_sub_order_status. Home delivery and
    pickup_point orders are both gated the same way at this step."""
    sub_order_id = await _checkout(client, buyer_user, product, _pickup_payload(pickup_point))
    vendor_headers = auth_headers(vendor_user)
    for target_status in ("confirmed", "preparing"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200, step.text

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status", json={"status": "shipped"}, headers=vendor_headers
    )

    assert response.status_code == 409


async def test_manager_can_set_and_clear_storage_location(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    product,
    pickup_point: PickupPoint,
) -> None:
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)
    manager_headers = auth_headers(manager_user)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/storage-location",
        json={"storage_location": "Étagère B3"},
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["storage_location"] == "Étagère B3"

    listing = await client.get("/orders/pickup-point-deliveries", headers=manager_headers)
    entry = next(so for so in listing.json() if so["id"] == sub_order_id)
    assert entry["storage_location"] == "Étagère B3"

    cleared = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/storage-location",
        json={"storage_location": None},
        headers=manager_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["storage_location"] is None


async def test_manager_of_another_point_cannot_set_storage_location(
    client: AsyncClient,
    db_session,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    product,
    pickup_point: PickupPoint,
) -> None:
    other_point = PickupPoint(name="Autre point", zone="Matoto")
    db_session.add(other_point)
    await db_session.flush()
    other_manager_user = await make_user(db_session, phone="+224620009994", role=UserRole.PICKUP_POINT_MANAGER)
    other_manager = PickupPointManager(user_id=other_manager_user.id, pickup_point_id=other_point.id)
    db_session.add(other_manager)
    await db_session.flush()

    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/storage-location",
        json={"storage_location": "Étagère B3"},
        headers=auth_headers(other_manager_user),
    )

    assert response.status_code == 403


async def test_courier_cannot_set_storage_location(
    client: AsyncClient,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    product,
    pickup_point: PickupPoint,
) -> None:
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/storage-location",
        json={"storage_location": "Étagère B3"},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 403


async def test_storage_location_rejected_for_home_delivery(
    client: AsyncClient,
    db_session,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    product,
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product, HOME_DELIVERY_PAYLOAD)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor_user),
    )

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/storage-location",
        json={"storage_location": "Étagère B3"},
        headers=auth_headers(manager_user),
    )

    assert response.status_code == 409
