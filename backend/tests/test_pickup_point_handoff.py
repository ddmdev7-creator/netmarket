"""Tests for the pickup_point two-step handoff: courier drops off at the
point (shipped -> arrived_at_pickup_point), then the pickup point manager
confirms the final handoff to the buyer (arrived_at_pickup_point ->
delivered). home_delivery must keep working exactly as before throughout."""

from httpx import AsyncClient

from app.couriers.models import Courier
from app.pickup_point_managers.models import PickupPointManager
from app.pickup_points.models import PickupPoint
from app.users.models import User, UserRole
from app.vendors.models import Vendor
from tests.conftest import auth_headers, make_user, scan_handoff

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

    response = await scan_handoff(client, courier_user, sub_order_id)

    assert response.status_code == 200
    assert response.json()["status"] == "delivered"


async def test_courier_cannot_mark_delivered_without_scanning(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product
) -> None:
    """La remise se confirme uniquement par scan du QR du client."""
    sub_order_id = await _checkout(client, buyer_user, product, HOME_DELIVERY_PAYLOAD)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor_user),
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=auth_headers(vendor_user)
        )

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 403


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
    """Avoir son propre code de dépôt ne suffit pas : un code n'est comparé
    qu'aux colis que la personne qui scanne doit réceptionner (voir
    confirm_delivery_by_code) — le livreur n'en fait pas partie."""
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    listing = await client.get("/orders/courier-deliveries", headers=auth_headers(courier_user))
    entry = next(so for so in listing.json() if so["id"] == sub_order_id)
    assert entry["dropoff_handoff_ready"] is True
    code = (
        await client.get(f"/orders/sub-orders/{sub_order_id}/handoff-code", headers=auth_headers(courier_user))
    ).json()["code"]

    response = await client.post(
        "/orders/sub-orders/confirm-delivery", json={"code": code}, headers=auth_headers(courier_user)
    )

    assert response.status_code == 409


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

    # Étape A : le gestionnaire scanne le code de dépôt affiché par le livreur.
    dropoff = await client.get(f"/orders/sub-orders/{sub_order_id}/handoff-code", headers=auth_headers(courier_user))
    assert dropoff.status_code == 200
    dropoff_code = dropoff.json()["code"]
    # Le QR ne contient aucune information lisible.
    assert dropoff_code.startswith("NDJ:") and sub_order_id not in dropoff_code

    step_a = await client.post(
        "/orders/sub-orders/confirm-delivery", json={"code": dropoff_code}, headers=auth_headers(manager_user)
    )
    assert step_a.status_code == 200
    assert step_a.json()["status"] == "arrived_at_pickup_point"

    # Un code déjà scanné ne sert plus.
    replay = await client.post(
        "/orders/sub-orders/confirm-delivery", json={"code": dropoff_code}, headers=auth_headers(manager_user)
    )
    assert replay.status_code == 409

    # Étape B : le gestionnaire scanne le QR de l'acheteur.
    order_view = await client.get("/orders", headers=auth_headers(buyer_user))
    order = next(o for o in order_view.json() if any(so["id"] == sub_order_id for so in o["sub_orders"]))
    sub_order = next(so for so in order["sub_orders"] if so["id"] == sub_order_id)
    assert sub_order["handoff_ready"] is True
    buyer_code = (
        await client.get(f"/orders/sub-orders/{sub_order_id}/handoff-code", headers=auth_headers(buyer_user))
    ).json()["code"]

    step_b = await client.post(
        "/orders/sub-orders/confirm-delivery", json={"code": buyer_code}, headers=auth_headers(manager_user)
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

    # Remise uniquement par scan : le bouton manuel est refusé, quelle que
    # soit l'étape.
    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(manager_user),
    )

    assert response.status_code == 403


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


async def test_admin_can_link_vendor_as_pickup_point_manager(
    client: AsyncClient, db_session, admin_user: User, vendor: Vendor, pickup_point: PickupPoint
) -> None:
    pickup_point.vendor_id = vendor.id
    await db_session.flush()

    response = await client.post(
        f"/admin/pickup-points/{pickup_point.id}/link-vendor-manager", headers=auth_headers(admin_user)
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == str(vendor.user_id)


async def test_linking_vendor_manager_fails_without_a_linked_vendor(
    client: AsyncClient, admin_user: User, pickup_point: PickupPoint
) -> None:
    response = await client.post(
        f"/admin/pickup-points/{pickup_point.id}/link-vendor-manager", headers=auth_headers(admin_user)
    )

    assert response.status_code == 409


async def test_vendor_linked_as_manager_can_use_pickup_manager_endpoints(
    client: AsyncClient,
    db_session,
    admin_user: User,
    vendor_user: User,
    vendor: Vendor,
    buyer_user: User,
    courier_user: User,
    courier: Courier,
    product,
    pickup_point: PickupPoint,
) -> None:
    pickup_point.vendor_id = vendor.id
    await db_session.flush()
    link = await client.post(
        f"/admin/pickup-points/{pickup_point.id}/link-vendor-manager", headers=auth_headers(admin_user)
    )
    assert link.status_code == 201

    vendor_headers = auth_headers(vendor_user)

    listing = await client.get("/orders/pickup-point-deliveries", headers=vendor_headers)
    assert listing.status_code == 200

    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)
    storage = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/storage-location",
        json={"storage_location": "Étagère B3"},
        headers=vendor_headers,
    )
    assert storage.status_code == 200
    assert storage.json()["storage_location"] == "Étagère B3"


async def test_manager_of_another_point_cannot_redeem_a_valid_code(
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
    other_manager_user = await make_user(db_session, phone="+224620009993", role=UserRole.PICKUP_POINT_MANAGER)
    db_session.add(PickupPointManager(user_id=other_manager_user.id, pickup_point_id=other_point.id))
    await db_session.flush()
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    response = await scan_handoff(client, other_manager_user, sub_order_id)

    assert response.status_code == 409


async def test_handoff_code_rotates_and_expires(
    client: AsyncClient, monkeypatch, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product
) -> None:
    import app.orders.handoff as handoff_module

    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(handoff_module.time, "time", lambda: clock["now"])

    sub_order_id = await _checkout(client, buyer_user, product, HOME_DELIVERY_PAYLOAD)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=auth_headers(vendor_user)
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=auth_headers(vendor_user)
        )

    first = (await client.get(f"/orders/sub-orders/{sub_order_id}/handoff-code", headers=auth_headers(buyer_user))).json()
    clock["now"] += 60
    second = (await client.get(f"/orders/sub-orders/{sub_order_id}/handoff-code", headers=auth_headers(buyer_user))).json()
    assert first["code"] != second["code"]

    # Deux créneaux plus tard, le premier code (photographié, par exemple) ne vaut plus rien.
    clock["now"] += 60
    stale = await client.post(
        "/orders/sub-orders/confirm-delivery", json={"code": first["code"]}, headers=auth_headers(courier_user)
    )
    assert stale.status_code == 409

    # Le code du créneau précédent est encore accepté (QR renouvelé pendant le scan).
    ok = await client.post(
        "/orders/sub-orders/confirm-delivery", json={"code": second["code"]}, headers=auth_headers(courier_user)
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "delivered"


async def test_only_the_buyer_or_dropping_courier_gets_a_code(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product, HOME_DELIVERY_PAYLOAD)
    # Pas encore expédiée : rien à présenter.
    early = await client.get(f"/orders/sub-orders/{sub_order_id}/handoff-code", headers=auth_headers(buyer_user))
    assert early.status_code == 404
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=auth_headers(vendor_user)
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=auth_headers(vendor_user)
        )
    for someone in (vendor_user, courier_user):
        response = await client.get(f"/orders/sub-orders/{sub_order_id}/handoff-code", headers=auth_headers(someone))
        assert response.status_code == 404


async def test_vendor_whose_shop_is_the_pickup_point_can_scan_the_courier_dropoff(
    client: AsyncClient,
    db_session,
    admin_user: User,
    vendor_user: User,
    vendor: Vendor,
    buyer_user: User,
    courier_user: User,
    courier: Courier,
    product,
    pickup_point: PickupPoint,
) -> None:
    """Régression : un vendeur également gestionnaire du point de retrait
    (sa boutique EST le point) doit pouvoir réceptionner ses propres colis."""
    pickup_point.vendor_id = vendor.id
    await db_session.flush()
    await client.post(f"/admin/pickup-points/{pickup_point.id}/link-vendor-manager", headers=auth_headers(admin_user))
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    arrival = await scan_handoff(client, vendor_user, sub_order_id)
    assert arrival.status_code == 200, arrival.text
    assert arrival.json()["status"] == "arrived_at_pickup_point"

    handed = await scan_handoff(client, vendor_user, sub_order_id)
    assert handed.status_code == 200, handed.text
    assert handed.json()["status"] == "delivered"


async def test_manager_sees_customer_and_can_update_opening_hours(
    client: AsyncClient,
    db_session,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    manager: PickupPointManager,
    product,
    pickup_point: PickupPoint,
) -> None:
    buyer_user.first_name, buyer_user.last_name = "Mariama", "Sow"
    await db_session.flush()
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)
    listing = await client.get("/orders/pickup-point-deliveries", headers=auth_headers(manager_user))
    entry = next(so for so in listing.json() if so["id"] == sub_order_id)
    assert entry["customer_name"] == "Mariama Sow"
    assert entry["customer_phone"] == buyer_user.phone
    assert entry["updated_at"]

    point = await client.get("/pickup-point-managers/me/point", headers=auth_headers(manager_user))
    assert point.status_code == 200 and point.json()["id"] == str(pickup_point.id)
    updated = await client.patch(
        "/pickup-point-managers/me/point", json={"opening_hours": "Lun–Ven 9h–19h"}, headers=auth_headers(manager_user)
    )
    assert updated.json()["opening_hours"] == "Lun–Ven 9h–19h"
    forbidden = await client.patch(
        "/pickup-point-managers/me/point", json={"opening_hours": "Tous les jours"}, headers=auth_headers(buyer_user)
    )
    assert forbidden.status_code == 403


async def test_parcel_changes_push_a_silent_refresh_to_courier_and_managers(
    client: AsyncClient,
    monkeypatch,
    buyer_user: User,
    vendor_user: User,
    courier_user: User,
    courier: Courier,
    manager_user: User,
    manager: PickupPointManager,
    product,
    pickup_point: PickupPoint,
) -> None:
    signals: list[tuple[set, str]] = []

    async def capture(user_ids, scope):
        signals.append((set(user_ids), scope))

    monkeypatch.setattr("app.orders.service.notifications_service.push_refresh", capture)
    sub_order_id = await _ship_pickup_order(client, buyer_user, vendor_user, courier_user, courier, product, pickup_point)

    # Affectation + 3 changements de statut : le livreur et le gestionnaire sont prévenus à chaque fois.
    assert len(signals) == 4
    assert all(ids == {courier_user.id, manager_user.id} and scope == "deliveries" for ids, scope in signals)

    await scan_handoff(client, manager_user, sub_order_id)
    assert len(signals) == 5
