"""Tests for vendor onboarding, own-profile management, public directory and admin validation."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from tests.conftest import auth_headers


async def test_register_vendor_promotes_role_and_is_pending(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User
) -> None:
    response = await client.post(
        "/vendors/me",
        json={"shop_name": "Ma Boutique", "zone": "Kaloum", "email": "vendeur@test.gn"},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    me = await client.get("/users/me", headers=auth_headers(buyer_user))
    assert me.json()["role"] == "vendor"


async def test_register_vendor_accepts_position(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User
) -> None:
    response = await client.post(
        "/vendors/me",
        json={"shop_name": "Ma Boutique", "email": "vendeur@test.gn", "latitude": 9.6412, "longitude": -13.5784},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 201
    assert response.json()["latitude"] == 9.6412
    assert response.json()["longitude"] == -13.5784


async def test_register_vendor_twice_fails(client: AsyncClient, buyer_user: User) -> None:
    headers = auth_headers(buyer_user)
    await client.post("/vendors/me", json={"shop_name": "Ma Boutique", "email": "vendeur@test.gn"}, headers=headers)

    response = await client.post(
        "/vendors/me", json={"shop_name": "Autre Nom", "email": "vendeur@test.gn"}, headers=headers
    )

    assert response.status_code == 409


async def test_get_my_vendor_without_registration_returns_404(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/vendors/me", headers=auth_headers(buyer_user))

    assert response.status_code == 404


async def test_new_vendor_defaults_to_one_day_preparation(
    client: AsyncClient, buyer_user: User
) -> None:
    response = await client.post(
        "/vendors/me", json={"shop_name": "Ma Boutique", "email": "vendeur@test.gn"}, headers=auth_headers(buyer_user)
    )

    assert response.json()["preparation_days"] == 1


async def test_vendor_can_update_preparation_days(client: AsyncClient, buyer_user: User) -> None:
    headers = auth_headers(buyer_user)
    await client.post("/vendors/me", json={"shop_name": "Ma Boutique", "email": "vendeur@test.gn"}, headers=headers)

    response = await client.patch("/vendors/me", json={"preparation_days": 3}, headers=headers)

    assert response.status_code == 200
    assert response.json()["preparation_days"] == 3


async def test_preparation_days_out_of_range_is_rejected(client: AsyncClient, buyer_user: User) -> None:
    headers = auth_headers(buyer_user)
    await client.post("/vendors/me", json={"shop_name": "Ma Boutique", "email": "vendeur@test.gn"}, headers=headers)

    response = await client.patch("/vendors/me", json={"preparation_days": 30}, headers=headers)

    assert response.status_code == 422


async def test_admin_cannot_register_a_shop(client: AsyncClient, admin_user: User) -> None:
    response = await client.post(
        "/vendors/me",
        json={"shop_name": "Boutique Admin", "email": "admin-shop@test.gn"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 403


async def test_admin_can_list_and_approve_pending_vendor(
    client: AsyncClient, buyer_user: User, admin_user: User
) -> None:
    register_response = await client.post(
        "/vendors/me",
        json={"shop_name": "Ma Boutique", "email": "vendeur@test.gn"},
        headers=auth_headers(buyer_user),
    )
    vendor_id = register_response.json()["id"]

    pending_list = await client.get("/admin/vendors", params={"status": "pending"}, headers=auth_headers(admin_user))
    assert pending_list.status_code == 200
    assert any(v["id"] == vendor_id for v in pending_list.json())

    approve_response = await client.patch(
        f"/admin/vendors/{vendor_id}", json={"status": "approved"}, headers=auth_headers(admin_user)
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"


async def test_non_admin_cannot_access_admin_vendor_endpoints(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/vendors", headers=auth_headers(buyer_user))

    assert response.status_code == 403


async def test_admin_listing_includes_the_linked_owner_account(
    client: AsyncClient, buyer_user: User, admin_user: User
) -> None:
    await client.post(
        "/vendors/me",
        json={"shop_name": "Ma Boutique", "email": "vendeur@test.gn"},
        headers=auth_headers(buyer_user),
    )

    listing = await client.get("/admin/vendors", params={"status": "pending"}, headers=auth_headers(admin_user))

    assert listing.status_code == 200
    vendor = next(v for v in listing.json() if v["shop_name"] == "Ma Boutique")
    assert vendor["owner_phone"] == "+224620000001"
    assert vendor["owner_email"] == "vendeur@test.gn"


async def test_public_listing_only_shows_approved_vendors(
    client: AsyncClient, buyer_user: User, admin_user: User
) -> None:
    register_response = await client.post(
        "/vendors/me",
        json={"shop_name": "Boutique En Attente", "email": "vendeur@test.gn"},
        headers=auth_headers(buyer_user),
    )
    vendor_id = register_response.json()["id"]

    public_before = await client.get("/vendors")
    assert not any(v["id"] == vendor_id for v in public_before.json())

    detail_before = await client.get(f"/vendors/{vendor_id}")
    assert detail_before.status_code == 404

    await client.patch(f"/admin/vendors/{vendor_id}", json={"status": "approved"}, headers=auth_headers(admin_user))

    public_after = await client.get("/vendors")
    assert any(v["id"] == vendor_id for v in public_after.json())

    detail_after = await client.get(f"/vendors/{vendor_id}")
    assert detail_after.status_code == 200
