"""Tests for courier ("livreur") onboarding, identity/vehicle document
verification, and admin validation."""

import io
import re

import pytest
from httpx import AsyncClient
from PIL import Image

from app.users.models import User, UserRole
from tests.conftest import auth_headers, make_user


def _stub_send_email(monkeypatch: pytest.MonkeyPatch, target: str) -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
        calls.append((to, subject, body))

    monkeypatch.setattr(target, fake_send_email)
    return calls


def _fake_jpeg(size: tuple[int, int] = (600, 600), color: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _registration_payload(**overrides: object) -> dict:
    payload = {
        "vehicle_type": "moto",
        "zone": "Kaloum",
        "id_document_type": "cni_biometrique",
        "id_document_front_key": "courier-docs/00000000-0000-0000-0000-000000000001.jpg",
        "id_document_back_key": "courier-docs/00000000-0000-0000-0000-000000000002.jpg",
        "face_photo_key": "courier-docs/00000000-0000-0000-0000-000000000003.jpg",
        "vehicle_name": "Yamaha DT125",
        "vehicle_plate_number": "RC-1234-AB",
        "vehicle_photo_keys": ["courier-docs/00000000-0000-0000-0000-000000000004.jpg"],
    }
    payload.update(overrides)
    return payload


async def test_register_courier_promotes_role_and_is_pending(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post("/couriers/me", json=_registration_payload(), headers=auth_headers(buyer_user))

    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    me = await client.get("/users/me", headers=auth_headers(buyer_user))
    assert me.json()["role"] == "courier"


async def test_register_courier_twice_fails(client: AsyncClient, buyer_user: User) -> None:
    headers = auth_headers(buyer_user)
    await client.post("/couriers/me", json=_registration_payload(), headers=headers)

    response = await client.post("/couriers/me", json=_registration_payload(vehicle_type="taxi"), headers=headers)

    assert response.status_code == 409


async def test_vendor_cannot_register_as_courier(client: AsyncClient, vendor_user: User) -> None:
    response = await client.post("/couriers/me", json=_registration_payload(), headers=auth_headers(vendor_user))

    assert response.status_code == 403


async def test_admin_cannot_register_as_courier(client: AsyncClient, admin_user: User) -> None:
    response = await client.post("/couriers/me", json=_registration_payload(), headers=auth_headers(admin_user))

    assert response.status_code == 403


async def test_cni_without_back_key_is_rejected(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me",
        json=_registration_payload(id_document_back_key=None),
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 409


async def test_passport_without_back_key_is_accepted(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me",
        json=_registration_payload(id_document_type="passeport", id_document_back_key=None),
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 201


async def test_public_listing_only_shows_approved_couriers(
    client: AsyncClient, buyer_user: User, admin_user: User
) -> None:
    register = await client.post(
        "/couriers/me", json=_registration_payload(vehicle_type="taxi", zone="Matam"), headers=auth_headers(buyer_user)
    )
    courier_id = register.json()["id"]

    before = await client.get("/couriers")
    assert not any(c["id"] == courier_id for c in before.json())

    approve = await client.patch(
        f"/admin/couriers/{courier_id}", json={"status": "approved"}, headers=auth_headers(admin_user)
    )
    assert approve.status_code == 200

    after = await client.get("/couriers")
    matching = next(c for c in after.json() if c["id"] == courier_id)
    assert matching["vehicle_type"] == "taxi"
    assert matching["phone"] == buyer_user.phone
    # L'annuaire public ne doit jamais exposer les documents de vérification.
    assert "id_document_front_key" not in matching


async def test_non_admin_cannot_validate_couriers(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/couriers", headers=auth_headers(buyer_user))

    assert response.status_code == 403


async def test_admin_invites_courier_by_email_instead_of_approving_directly(
    client: AsyncClient, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_send_email(monkeypatch, "app.couriers.service.send_email")

    response = await client.post(
        "/admin/couriers",
        json={
            "phone": "+224655000099",
            "email": "fatoumata@example.com",
            "first_name": "Fatoumata",
            "last_name": "Barry",
        },
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["phone"] == "+224655000099"
    assert body["email"] == "fatoumata@example.com"
    assert len(calls) == 1
    assert calls[0][0] == "fatoumata@example.com"

    # Pas encore un livreur : compte acheteur en attendant l'activation, et
    # aucune fiche Courier tant que le profil n'est pas complété soi-même.
    listing = await client.get("/admin/couriers", params={"status": "pending"}, headers=auth_headers(admin_user))
    assert listing.json() == []


async def test_admin_create_courier_rejects_duplicate_phone(client: AsyncClient, admin_user: User, buyer_user: User) -> None:
    response = await client.post(
        "/admin/couriers",
        json={"phone": buyer_user.phone, "email": "someone-else@example.com"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 409


async def test_admin_create_courier_rejects_duplicate_email(client: AsyncClient, admin_user: User) -> None:
    await client.post(
        "/auth/register",
        json={"phone": "+224655000094", "password": "password123", "email": "taken@example.com"},
    )

    response = await client.post(
        "/admin/couriers",
        json={"phone": "+224655000097", "email": "taken@example.com"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 409


async def test_non_admin_cannot_create_courier(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/admin/couriers",
        json={"phone": "+224655000098", "email": "someone@example.com"},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 403


async def test_courier_invitation_full_loop_activates_and_logs_in(
    client: AsyncClient, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_send_email(monkeypatch, "app.couriers.service.send_email")

    invite = await client.post(
        "/admin/couriers",
        json={"phone": "+224655000096", "email": "invited@example.com"},
        headers=auth_headers(admin_user),
    )
    assert invite.status_code == 201
    code = re.search(r"\d{5}", calls[0][2]).group()

    activate = await client.post(
        "/auth/accept-courier-invitation",
        json={"phone": "+224655000096", "code": code, "new_password": "new-password123"},
    )
    assert activate.status_code == 200

    login = await client.post(
        "/auth/login", json={"phone": "+224655000096", "password": "new-password123"}
    )
    assert login.status_code == 200

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["role"] == "buyer"
    assert me.json()["email_verified"] is True


async def test_courier_invitation_rejects_wrong_code(client: AsyncClient, admin_user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_send_email(monkeypatch, "app.couriers.service.send_email")
    await client.post(
        "/admin/couriers",
        json={"phone": "+224655000095", "email": "wrongcode@example.com"},
        headers=auth_headers(admin_user),
    )

    response = await client.post(
        "/auth/accept-courier-invitation",
        json={"phone": "+224655000095", "code": "00000", "new_password": "new-password123"},
    )

    assert response.status_code == 409


async def test_admin_reject_without_reason_fails(client: AsyncClient, buyer_user: User, admin_user: User) -> None:
    register = await client.post("/couriers/me", json=_registration_payload(), headers=auth_headers(buyer_user))
    courier_id = register.json()["id"]

    response = await client.patch(
        f"/admin/couriers/{courier_id}", json={"status": "rejected"}, headers=auth_headers(admin_user)
    )

    assert response.status_code == 409


async def test_admin_reject_with_reason_notifies_courier(client: AsyncClient, buyer_user: User, admin_user: User) -> None:
    register = await client.post("/couriers/me", json=_registration_payload(), headers=auth_headers(buyer_user))
    courier_id = register.json()["id"]

    response = await client.patch(
        f"/admin/couriers/{courier_id}",
        json={"status": "rejected", "admin_note": "Photo de visage illisible, à refaire."},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 200
    assert response.json()["admin_note"] == "Photo de visage illisible, à refaire."

    notifications = await client.get("/notifications", headers=auth_headers(buyer_user))
    assert any(n["type"] == "courier_verification_rejected" for n in notifications.json()["items"])


async def test_admin_approve_notifies_courier(client: AsyncClient, buyer_user: User, admin_user: User) -> None:
    register = await client.post("/couriers/me", json=_registration_payload(), headers=auth_headers(buyer_user))
    courier_id = register.json()["id"]

    response = await client.patch(
        f"/admin/couriers/{courier_id}", json={"status": "approved"}, headers=auth_headers(admin_user)
    )

    assert response.status_code == 200
    notifications = await client.get("/notifications", headers=auth_headers(buyer_user))
    assert any(n["type"] == "courier_verification_approved" for n in notifications.json()["items"])


async def test_buyer_can_upload_courier_document(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me/documents",
        data={"slot": "id_front"},
        files=[("files", ("cni.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 200
    keys = response.json()["keys"]
    assert len(keys) == 1
    assert keys[0].startswith("courier-docs/")


async def test_vendor_cannot_upload_courier_document(client: AsyncClient, vendor_user: User) -> None:
    response = await client.post(
        "/couriers/me/documents",
        data={"slot": "id_front"},
        files=[("files", ("cni.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 403


async def test_single_slot_rejects_more_than_one_file(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me/documents",
        data={"slot": "face"},
        files=[
            ("files", ("a.jpg", _fake_jpeg(), "image/jpeg")),
            ("files", ("b.jpg", _fake_jpeg(), "image/jpeg")),
        ],
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 409


async def test_vehicle_slot_accepts_up_to_four_files(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me/documents",
        data={"slot": "vehicle"},
        files=[("files", (f"v{i}.jpg", _fake_jpeg(), "image/jpeg")) for i in range(4)],
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 200
    assert len(response.json()["keys"]) == 4


async def test_face_photo_below_minimum_resolution_is_rejected(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me/documents",
        data={"slot": "face"},
        files=[("files", ("face.jpg", _fake_jpeg(size=(300, 300)), "image/jpeg"))],
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 409


async def test_id_document_slot_has_no_minimum_resolution(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/couriers/me/documents",
        data={"slot": "id_front"},
        files=[("files", ("cni.jpg", _fake_jpeg(size=(300, 300)), "image/jpeg"))],
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 200


async def test_courier_can_read_own_document(client: AsyncClient, buyer_user: User) -> None:
    upload = await client.post(
        "/couriers/me/documents",
        data={"slot": "face"},
        files=[("files", ("face.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(buyer_user),
    )
    key = upload.json()["keys"][0]
    register = await client.post(
        "/couriers/me", json=_registration_payload(face_photo_key=key), headers=auth_headers(buyer_user)
    )
    courier_id = register.json()["id"]

    response = await client.get(f"/couriers/{courier_id}/documents/{key}", headers=auth_headers(buyer_user))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


async def test_admin_can_read_courier_document(client: AsyncClient, buyer_user: User, admin_user: User) -> None:
    upload = await client.post(
        "/couriers/me/documents",
        data={"slot": "face"},
        files=[("files", ("face.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(buyer_user),
    )
    key = upload.json()["keys"][0]
    register = await client.post(
        "/couriers/me", json=_registration_payload(face_photo_key=key), headers=auth_headers(buyer_user)
    )
    courier_id = register.json()["id"]

    response = await client.get(f"/couriers/{courier_id}/documents/{key}", headers=auth_headers(admin_user))

    assert response.status_code == 200


async def test_other_courier_cannot_read_document(client: AsyncClient, buyer_user: User, db_session) -> None:
    upload = await client.post(
        "/couriers/me/documents",
        data={"slot": "face"},
        files=[("files", ("face.jpg", _fake_jpeg(), "image/jpeg"))],
        headers=auth_headers(buyer_user),
    )
    key = upload.json()["keys"][0]
    register = await client.post(
        "/couriers/me", json=_registration_payload(face_photo_key=key), headers=auth_headers(buyer_user)
    )
    courier_id = register.json()["id"]

    other_buyer = await make_user(db_session, phone="+224620000099", role=UserRole.BUYER)
    response = await client.get(f"/couriers/{courier_id}/documents/{key}", headers=auth_headers(other_buyer))

    assert response.status_code == 403


async def test_document_key_not_belonging_to_courier_is_404(client: AsyncClient, buyer_user: User) -> None:
    register = await client.post("/couriers/me", json=_registration_payload(), headers=auth_headers(buyer_user))
    courier_id = register.json()["id"]

    response = await client.get(
        f"/couriers/{courier_id}/documents/courier-docs/00000000-0000-0000-0000-000000000099.jpg",
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 404


async def test_going_online_without_coordinates_is_rejected(client: AsyncClient, courier_user: User) -> None:
    response = await client.patch(
        "/couriers/me/availability", json={"is_online": True}, headers=auth_headers(courier_user)
    )

    assert response.status_code == 409


async def test_going_online_with_coordinates_succeeds(client: AsyncClient, courier_user: User) -> None:
    response = await client.patch(
        "/couriers/me/availability",
        json={"is_online": True, "latitude": 9.64, "longitude": -13.58},
        headers=auth_headers(courier_user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_online"] is True
    assert body["latitude"] == 9.64


async def test_going_offline_does_not_require_coordinates(client: AsyncClient, courier_user: User) -> None:
    await client.patch(
        "/couriers/me/availability",
        json={"is_online": True, "latitude": 9.64, "longitude": -13.58},
        headers=auth_headers(courier_user),
    )

    response = await client.patch(
        "/couriers/me/availability", json={"is_online": False}, headers=auth_headers(courier_user)
    )

    assert response.status_code == 200
    assert response.json()["is_online"] is False
    # La position enregistrée n'est pas effacée en repassant hors ligne — le
    # prochain passage en ligne pourra la réutiliser sans la redemander.
    assert response.json()["latitude"] == 9.64


async def test_vendor_cannot_set_courier_availability(client: AsyncClient, vendor_user: User) -> None:
    response = await client.patch(
        "/couriers/me/availability",
        json={"is_online": True, "latitude": 9.64, "longitude": -13.58},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 403
