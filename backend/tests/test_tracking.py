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
