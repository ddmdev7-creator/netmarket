"""Suivi en direct du livreur pendant une course."""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User
from tests.conftest import auth_headers
from tests.test_vendor_dashboard import _advance_to, _checkout


async def test_courier_position_is_pushed_and_visible_only_while_shipped(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    order = await _checkout(client, buyer_user, product)
    sub_order_id = order["sub_orders"][0]["id"]
    await _advance_to(client, vendor_user, sub_order_id, "preparing", courier, courier_user)
    position = {"latitude": 9.55, "longitude": -13.66}

    # Pas encore expédié : la position n'est partagée avec personne.
    with patch("app.orders.tracking.ws_manager.send_to_user", new=AsyncMock()) as push:
        ack = await client.post("/couriers/me/position", json=position, headers=auth_headers(courier_user))
    assert ack.json() == {"tracked_deliveries": 0}
    push.assert_not_called()
    tracking = (await client.get(f"/orders/sub-orders/{sub_order_id}/tracking", headers=auth_headers(buyer_user))).json()
    assert tracking["courier_latitude"] is None

    await client.patch(f"/orders/sub-orders/{sub_order_id}/status", json={"status": "shipped"}, headers=auth_headers(vendor_user))
    with patch("app.orders.tracking.ws_manager.send_to_user", new=AsyncMock()) as push:
        ack = await client.post("/couriers/me/position", json=position, headers=auth_headers(courier_user))
    assert ack.json() == {"tracked_deliveries": 1}
    buyer_id, payload = push.call_args.args
    assert buyer_id == buyer_user.id
    assert payload["type"] == "courier_position" and payload["sub_order_id"] == sub_order_id

    tracking = (await client.get(f"/orders/sub-orders/{sub_order_id}/tracking", headers=auth_headers(buyer_user))).json()
    assert tracking["status"] == "shipped"
    assert (tracking["courier_latitude"], tracking["courier_longitude"]) == (9.55, -13.66)
    assert tracking["courier_position_at"] is not None


async def test_tracking_is_private_to_the_buyer(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product
) -> None:
    order = await _checkout(client, buyer_user, product)
    sub_order_id = order["sub_orders"][0]["id"]

    response = await client.get(f"/orders/sub-orders/{sub_order_id}/tracking", headers=auth_headers(vendor_user))
    assert response.status_code == 404


async def test_only_couriers_can_share_a_position(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me/position", json={"latitude": 9.5, "longitude": -13.6}, headers=auth_headers(buyer_user)
    )
    assert response.status_code == 403


async def test_tracking_and_admin_monitor_include_route_and_positions(
    client: AsyncClient,
    monkeypatch,
    buyer_user: User,
    vendor_user: User,
    admin_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
) -> None:
    fake_route = {"coordinates": [[-13.67, 9.54], [-13.66, 9.55]], "distance_km": 3.2, "duration_min": 9}

    async def _route(points):
        return fake_route

    monkeypatch.setattr("app.routing.service.get_route", _route)
    order = await _checkout(client, buyer_user, product)
    sub_order_id = order["sub_orders"][0]["id"]
    await _advance_to(client, vendor_user, sub_order_id, "shipped", courier, courier_user)

    with patch("app.orders.tracking.ws_manager.send_to_user", new=AsyncMock()) as push:
        await client.post("/couriers/me/position", json={"latitude": 9.55, "longitude": -13.66}, headers=auth_headers(courier_user))
    recipients = {call.args[0] for call in push.call_args_list}
    assert recipients == {buyer_user.id, admin_user.id}

    tracking = (await client.get(f"/orders/sub-orders/{sub_order_id}/tracking", headers=auth_headers(buyer_user))).json()
    # Sans position GPS de livraison, pas de destination donc pas de trajet.
    assert tracking["route"] is None or tracking["route"]["distance_km"] == 3.2

    monitor = (
        await client.get("/admin/deliveries/monitor", params={"with_routes": True}, headers=auth_headers(admin_user))
    ).json()
    entry = next(e for e in monitor["entries"] if e["sub_order_id"] == sub_order_id)
    assert entry["courier_live"] is True
    assert (entry["courier_latitude"], entry["courier_longitude"]) == (9.55, -13.66)
