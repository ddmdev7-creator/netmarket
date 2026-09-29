"""Fiches admin : utilisateur, livreur, point de retrait, gestionnaires, abonnements."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.couriers.models import Courier
from app.pickup_point_managers.models import PickupPointManager
from app.pickup_points.models import PickupPoint
from app.users.models import User
from tests.conftest import auth_headers


async def test_user_profile_and_update(client: AsyncClient, admin_user: User, buyer_user: User) -> None:
    headers = auth_headers(admin_user)
    profile = (await client.get(f"/admin/users/{buyer_user.id}/profile", headers=headers)).json()
    assert profile["phone"] == buyer_user.phone and profile["orders_count"] == 0 and profile["vendor"] is None

    updated = (
        await client.patch(
            f"/admin/users/{buyer_user.id}", json={"first_name": "Aïssatou", "is_active": False}, headers=headers
        )
    ).json()
    assert updated["first_name"] == "Aïssatou" and updated["is_active"] is False

    # Un compte désactivé ne peut plus appeler l'API.
    assert (await client.get("/users/me", headers=auth_headers(buyer_user))).status_code == 401


async def test_admin_cannot_deactivate_self(client: AsyncClient, admin_user: User) -> None:
    response = await client.patch(f"/admin/users/{admin_user.id}", json={"is_active": False}, headers=auth_headers(admin_user))
    assert response.status_code == 409


async def test_courier_profile_and_edit(client: AsyncClient, admin_user: User, courier: Courier) -> None:
    headers = auth_headers(admin_user)
    profile = (await client.get(f"/admin/couriers/{courier.id}/profile", headers=headers)).json()
    assert profile["courier"]["id"] == str(courier.id)
    assert profile["stats"] == {"delivered": 0, "in_progress": 0, "cancelled": 0, "delivered_30d": 0}

    edited = (
        await client.patch(f"/admin/couriers/{courier.id}", json={"vehicle_plate_number": "RC-1234-A", "zone": "Ratoma"}, headers=headers)
    ).json()
    assert edited["vehicle_plate_number"] == "RC-1234-A" and edited["zone"] == "Ratoma"


async def test_pickup_point_profile_and_managers_overview(
    client: AsyncClient, admin_user: User, pickup_point: PickupPoint, manager: PickupPointManager
) -> None:
    headers = auth_headers(admin_user)
    profile = (await client.get(f"/admin/pickup-points/{pickup_point.id}/profile", headers=headers)).json()
    assert profile["point"]["id"] == str(pickup_point.id)
    assert [m["id"] for m in profile["managers"]] == [str(manager.id)]
    assert profile["stats"]["in_stock"] == 0

    overview = (await client.get("/admin/pickup-point-managers/overview", headers=headers)).json()
    assert overview[0]["pickup_point_name"] == pickup_point.name and overview[0]["is_active"] is True


async def test_admin_subscriptions_include_owner(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, vendor_user: User, subscription_plan
) -> None:
    await client.post("/subscriptions/subscribe", json={"plan_id": str(subscription_plan.id)}, headers=auth_headers(vendor_user))
    rows = (await client.get("/admin/subscriptions", headers=auth_headers(admin_user))).json()
    assert rows[0]["shop_name"] == "Boutique Test"
    assert rows[0]["owner_phone"] == vendor_user.phone and rows[0]["created_at"]
