"""Tests for assigning a courier to a sub-order, and the courier's own
delivery-confirmation capabilities (manual and QR scan)."""

from httpx import AsyncClient

from app.couriers.models import Courier, CourierStatus, VehicleType
from app.users.models import User, UserRole
from tests.conftest import auth_headers, make_user, make_vendor, scan_handoff

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


async def _checkout(client: AsyncClient, buyer: User, product) -> str:
    await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer)
    )
    response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer))
    return response.json()["sub_orders"][0]["id"]


async def test_vendor_can_assign_courier(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier: Courier, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 200
    assert response.json()["courier_id"] == str(courier.id)
    assert response.json()["courier_phone"] == "+224620000005"


async def test_cannot_assign_unapproved_courier(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, product
) -> None:
    pending_courier_user = await make_user(db_session, phone="+224620009998", role=UserRole.COURIER)
    pending_courier = Courier(user_id=pending_courier_user.id, vehicle_type=VehicleType.MOTO, status=CourierStatus.PENDING)
    db_session.add(pending_courier)
    await db_session.flush()

    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(pending_courier.id)},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 409


async def test_other_vendor_cannot_assign_courier_to_foreign_sub_order(
    client: AsyncClient, db_session, buyer_user: User, courier: Courier, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)
    other_vendor_user, _ = await make_vendor(db_session, phone="+224620009997", shop_name="Autre Boutique")

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(other_vendor_user),
    )

    assert response.status_code == 403


async def test_assigned_courier_sees_delivery_in_own_list(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor_user),
    )

    response = await client.get("/orders/courier-deliveries", headers=auth_headers(courier_user))

    assert response.status_code == 200
    assert any(so["id"] == sub_order_id for so in response.json())


async def test_courier_can_only_mark_delivered_not_other_transitions(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier",
        json={"courier_id": str(courier.id)},
        headers=auth_headers(vendor_user),
    )

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "confirmed"},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 403


async def test_vendor_cannot_mark_shipped_without_a_courier(
    client: AsyncClient, buyer_user: User, vendor_user: User, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)
    vendor_headers = auth_headers(vendor_user)
    for target_status in ("confirmed", "preparing"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status", json={"status": "shipped"}, headers=vendor_headers
    )

    assert response.status_code == 409
    assert "livreur" in response.json()["detail"]


async def test_assigned_courier_can_mark_delivered_once_shipped(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier_user: User, courier: Courier, product
) -> None:
    sub_order_id = await _checkout(client, buyer_user, product)
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


async def test_vendor_cannot_mark_delivered_directly(
    client: AsyncClient, buyer_user: User, vendor_user: User, courier: Courier, product
) -> None:
    """Only the assigned courier confirms remise au client for a home
    delivery — see update_sub_order_status's is_owner_vendor guard."""
    sub_order_id = await _checkout(client, buyer_user, product)
    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status", json={"status": "delivered"}, headers=vendor_headers
    )

    assert response.status_code == 403


async def test_unassigned_courier_cannot_mark_delivered(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, product
) -> None:
    other_courier_user = await make_user(db_session, phone="+224620009996", role=UserRole.COURIER)
    other_courier = Courier(user_id=other_courier_user.id, vehicle_type=VehicleType.TAXI, status=CourierStatus.APPROVED)
    db_session.add(other_courier)
    await db_session.flush()

    sub_order_id = await _checkout(client, buyer_user, product)

    response = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "confirmed"},
        headers=auth_headers(other_courier_user),
    )

    assert response.status_code == 403
