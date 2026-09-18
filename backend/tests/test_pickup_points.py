"""Tests for admin-managed pickup points: admin CRUD, public read-only listing."""

from httpx import AsyncClient

from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers


async def test_admin_can_create_pickup_point(client: AsyncClient, admin_user: User) -> None:
    response = await client.post(
        "/admin/pickup-points",
        json={"name": "Point Wari Madina", "zone": "En face de la pharmacie", "latitude": 9.537, "longitude": -13.6785},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Point Wari Madina"
    assert body["is_active"] is True


async def test_non_admin_cannot_create_pickup_point(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/admin/pickup-points", json={"name": "Point Test", "zone": "Kaloum"}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 403


async def test_public_listing_only_shows_active_points(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    active = await client.post("/admin/pickup-points", json={"name": "Actif", "zone": "Kaloum"}, headers=headers)
    inactive_resp = await client.post(
        "/admin/pickup-points", json={"name": "Inactif", "zone": "Matam", "is_active": False}, headers=headers
    )

    public = await client.get("/pickup-points")

    names = [p["name"] for p in public.json()]
    assert "Actif" in names
    assert "Inactif" not in names
    assert inactive_resp.json()["is_active"] is False
    assert active.json()["is_active"] is True


async def test_admin_listing_includes_inactive_points(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    await client.post("/admin/pickup-points", json={"name": "Inactif", "zone": "Matam", "is_active": False}, headers=headers)

    admin_listing = await client.get("/admin/pickup-points", headers=headers)

    names = [p["name"] for p in admin_listing.json()]
    assert "Inactif" in names


async def test_admin_can_update_pickup_point(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    created = await client.post("/admin/pickup-points", json={"name": "Point A", "zone": "Kaloum"}, headers=headers)

    response = await client.patch(
        f"/admin/pickup-points/{created.json()['id']}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_admin_can_delete_pickup_point(client: AsyncClient, admin_user: User) -> None:
    headers = auth_headers(admin_user)
    created = await client.post("/admin/pickup-points", json={"name": "Point A", "zone": "Kaloum"}, headers=headers)

    response = await client.delete(f"/admin/pickup-points/{created.json()['id']}", headers=headers)

    assert response.status_code == 200
    listing = await client.get("/admin/pickup-points", headers=headers)
    assert listing.json() == []


async def test_admin_can_link_pickup_point_to_a_vendor(client: AsyncClient, admin_user: User, vendor: Vendor) -> None:
    response = await client.post(
        "/admin/pickup-points",
        json={"name": "Boutique Test — retrait", "zone": "Kaloum", "vendor_id": str(vendor.id)},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["vendor_id"] == str(vendor.id)
    assert body["vendor_shop_name"] == "Boutique Test"


async def test_admin_cannot_link_pickup_point_to_an_unknown_vendor(client: AsyncClient, admin_user: User) -> None:
    response = await client.post(
        "/admin/pickup-points",
        json={"name": "Point orphelin", "zone": "Kaloum", "vendor_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 404


async def test_admin_can_unlink_pickup_point_from_its_vendor(
    client: AsyncClient, admin_user: User, vendor: Vendor
) -> None:
    headers = auth_headers(admin_user)
    created = await client.post(
        "/admin/pickup-points",
        json={"name": "Boutique Test — retrait", "zone": "Kaloum", "vendor_id": str(vendor.id)},
        headers=headers,
    )

    response = await client.patch(
        f"/admin/pickup-points/{created.json()['id']}", json={"vendor_id": None}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["vendor_id"] is None
    assert response.json()["vendor_shop_name"] is None
