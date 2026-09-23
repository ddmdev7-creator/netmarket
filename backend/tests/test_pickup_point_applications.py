"""Candidatures gestionnaire de point de retrait : dossier, contrôles de la
photo d'identité, soumission, seconde chance, refus définitif, invitation,
validation (création du point + du gestionnaire)."""

import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification, NotificationType
from app.pickup_point_managers.models import PickupPointManager
from app.pickup_points.models import PickupPoint
from app.users.models import User, UserRole
from tests.conftest import auth_headers, make_user


def _png(width: int, height: int, color=(255, 255, 255)) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (width, height), color)
    # Un « visage » au centre, pour ne pas être une image entièrement unie.
    for x in range(width // 3, 2 * width // 3):
        for y in range(height // 3, height):
            image.putpixel((x, y), (120, 90, 70))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _key() -> str:
    return f"pickup-applications/{uuid.uuid4()}.jpg"


COMPLETE = {
    "first_name": "Aïssatou",
    "last_name": "Barry",
    "birth_date": "1994-03-12",
    "residence_address": "Ratoma, Kipé",
    "id_document_type": "cni_biometrique",
    "id_document_number": "GN123456",
    "point_name": "Relais Kipé",
    "point_address": "Kipé, carrefour Kakimbo",
    "point_landmark": "En face de la pharmacie",
    "latitude": 9.57,
    "longitude": -13.64,
    "opening_hours": "Lun–Sam 8h–20h",
    "storage_capacity": 40,
}


@pytest.fixture(autouse=True)
def _stub_storage_and_email(monkeypatch: pytest.MonkeyPatch) -> list:
    sent: list = []

    def fake_upload(content: bytes, *, prefix: str = "") -> str:
        return f"{prefix}{uuid.uuid4()}.jpg"

    async def fake_send(to, subject, text, html):
        sent.append((to, subject))

    monkeypatch.setattr("app.pickup_point_applications.service.upload_image", fake_upload)
    monkeypatch.setattr("app.pickup_point_applications.service.send_email", fake_send)
    return sent


def _complete_payload() -> dict:
    return {
        **COMPLETE,
        "id_document_front_key": _key(),
        "id_document_back_key": _key(),
        "portrait_photo_key": _key(),
        "premises_photo_keys": [_key() for _ in range(4)],
    }


async def _submit_complete(client: AsyncClient, buyer: User) -> dict:
    saved = await client.put("/pickup-point-applications/me", json=_complete_payload(), headers=auth_headers(buyer))
    assert saved.status_code == 200, saved.text
    submitted = await client.post("/pickup-point-applications/me/submit", headers=auth_headers(buyer))
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


async def _upload(client: AsyncClient, user: User, slot: str, *images: bytes):
    files = [("files", (f"p{i}.png", content, "image/png")) for i, content in enumerate(images)]
    return await client.post(
        "/pickup-point-applications/me/documents", data={"slot": slot}, files=files, headers=auth_headers(user)
    )


async def test_portrait_photo_must_be_hd_portrait_on_white(client: AsyncClient, buyer_user: User) -> None:
    ok = await _upload(client, buyer_user, "portrait", _png(600, 800))
    assert ok.status_code == 201, ok.text
    assert ok.json()["keys"][0].startswith("pickup-applications/")

    too_small = await _upload(client, buyer_user, "portrait", _png(300, 400))
    assert too_small.status_code == 409
    landscape = await _upload(client, buyer_user, "portrait", _png(1000, 700))
    assert landscape.status_code == 409
    red_background = await _upload(client, buyer_user, "portrait", _png(600, 800, color=(200, 30, 30)))
    assert red_background.status_code == 409
    assert "fond blanc" in red_background.json()["detail"]


async def test_premises_photos_are_limited_and_checked(client: AsyncClient, buyer_user: User) -> None:
    small = await _upload(client, buyer_user, "premises", _png(300, 200))
    assert small.status_code == 409
    many = await _upload(client, buyer_user, "premises", *[_png(800, 600) for _ in range(9)])
    assert many.status_code == 409
    four = await _upload(client, buyer_user, "premises", *[_png(800, 600) for _ in range(4)])
    assert four.status_code == 201
    assert len(four.json()["keys"]) == 4


async def test_incomplete_application_cannot_be_submitted(client: AsyncClient, buyer_user: User) -> None:
    state = (await client.get("/pickup-point-applications/me", headers=auth_headers(buyer_user))).json()
    assert state["can_apply"] is True and state["application"] is None

    await client.put(
        "/pickup-point-applications/me",
        json={"first_name": "Aïssatou", "premises_photo_keys": [_key()]},
        headers=auth_headers(buyer_user),
    )
    response = await client.post("/pickup-point-applications/me/submit", headers=auth_headers(buyer_user))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "photo d'identité" in detail and "au moins 4 photos du local" in detail


async def test_foreign_document_keys_are_refused(client: AsyncClient, buyer_user: User) -> None:
    response = await client.put(
        "/pickup-point-applications/me",
        json={"portrait_photo_key": "courier-docs/0f3b1a3e-3b5c-4f0e-9a38-4c1b8f4f2a11.jpg"},
        headers=auth_headers(buyer_user),
    )
    assert response.status_code == 409


async def test_submission_notifies_admins_and_locks_the_dossier(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, admin_user: User
) -> None:
    application = await _submit_complete(client, buyer_user)
    assert application["status"] == "submitted"
    assert application["submission_count"] == 1

    notifications = (
        await db_session.execute(select(Notification).where(Notification.user_id == admin_user.id))
    ).scalars().all()
    assert [n.type for n in notifications] == [NotificationType.PICKUP_APPLICATION_SUBMITTED]

    locked = await client.put("/pickup-point-applications/me", json=_complete_payload(), headers=auth_headers(buyer_user))
    assert locked.status_code == 409


async def test_second_chance_reopens_the_dossier(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, admin_user: User, _stub_storage_and_email: list
) -> None:
    buyer_user.email = "candidat@example.com"
    await db_session.flush()
    application = await _submit_complete(client, buyer_user)
    response = await client.post(
        f"/admin/pickup-point-applications/{application['id']}/request-changes",
        json={"reason": "Photo du local trop sombre", "suggestion": "Reprenez les photos en journée"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "changes_requested"

    state = (await client.get("/pickup-point-applications/me", headers=auth_headers(buyer_user))).json()
    assert state["application"]["admin_note"] == "Photo du local trop sombre"
    assert state["application"]["admin_suggestion"] == "Reprenez les photos en journée"
    assert _stub_storage_and_email == [("candidat@example.com", "Votre dossier est à corriger — Marketplace Guinée")]

    resubmitted = await _submit_complete(client, buyer_user)
    assert resubmitted["status"] == "submitted"
    assert resubmitted["submission_count"] == 2


async def test_definitive_rejection_blocks_the_account_until_invited(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, admin_user: User
) -> None:
    buyer_user.email = "aissatou@example.com"
    await db_session.flush()
    application = await _submit_complete(client, buyer_user)
    rejected = await client.post(
        f"/admin/pickup-point-applications/{application['id']}/reject",
        json={"reason": "Local inadapté"},
        headers=auth_headers(admin_user),
    )
    assert rejected.json()["status"] == "rejected"

    state = (await client.get("/pickup-point-applications/me", headers=auth_headers(buyer_user))).json()
    assert state["can_apply"] is False
    blocked = await client.put("/pickup-point-applications/me", json=COMPLETE, headers=auth_headers(buyer_user))
    assert blocked.status_code == 403

    invited = await client.post(
        "/admin/pickup-point-applications/invite",
        json={"email": "AISSATOU@example.com"},
        headers=auth_headers(admin_user),
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["status"] == "draft"
    assert invited.json()["origin"] == "invited"
    reopened = await client.put("/pickup-point-applications/me", json=COMPLETE, headers=auth_headers(buyer_user))
    assert reopened.status_code == 200


async def test_invitation_requires_an_existing_buyer_account(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, vendor_user: User
) -> None:
    unknown = await client.post(
        "/admin/pickup-point-applications/invite", json={"email": "personne@example.com"}, headers=auth_headers(admin_user)
    )
    assert unknown.status_code == 404
    vendor_user.email = "vendeur@example.com"
    await db_session.flush()
    not_buyer = await client.post(
        "/admin/pickup-point-applications/invite", json={"email": "vendeur@example.com"}, headers=auth_headers(admin_user)
    )
    assert not_buyer.status_code == 409


async def test_non_buyer_cannot_apply(client: AsyncClient, vendor_user: User) -> None:
    state = (await client.get("/pickup-point-applications/me", headers=auth_headers(vendor_user))).json()
    assert state["can_apply"] is False
    response = await client.put("/pickup-point-applications/me", json=COMPLETE, headers=auth_headers(vendor_user))
    assert response.status_code == 403


async def test_approval_creates_the_point_and_the_manager(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, admin_user: User
) -> None:
    application = await _submit_complete(client, buyer_user)
    response = await client.post(
        f"/admin/pickup-point-applications/{application['id']}/approve", headers=auth_headers(admin_user)
    )
    assert response.status_code == 200, response.text
    approved = response.json()
    assert approved["status"] == "approved"

    point = await db_session.get(PickupPoint, uuid.UUID(approved["pickup_point_id"]))
    assert point.name == "Relais Kipé"
    assert point.opening_hours == "Lun–Sam 8h–20h"
    assert "pharmacie" in point.zone
    manager = (
        await db_session.execute(select(PickupPointManager).where(PickupPointManager.user_id == buyer_user.id))
    ).scalar_one()
    assert manager.pickup_point_id == point.id
    await db_session.refresh(buyer_user)
    assert buyer_user.role == UserRole.PICKUP_POINT_MANAGER

    listing = await client.get("/orders/pickup-point-deliveries", headers=auth_headers(buyer_user))
    assert listing.status_code == 200
    again = await client.post(
        f"/admin/pickup-point-applications/{application['id']}/approve", headers=auth_headers(admin_user)
    )
    assert again.status_code == 409


async def test_documents_are_private(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, buyer_user: User, admin_user: User
) -> None:
    monkeypatch.setattr("app.pickup_point_applications.router.fetch_image", lambda key: b"jpeg-bytes")
    payload = _complete_payload()
    saved = (
        await client.put("/pickup-point-applications/me", json=payload, headers=auth_headers(buyer_user))
    ).json()
    url = f"/pickup-point-applications/{saved['id']}/documents/{payload['portrait_photo_key']}"

    assert (await client.get(url, headers=auth_headers(buyer_user))).status_code == 200
    assert (await client.get(url, headers=auth_headers(admin_user))).status_code == 200
    stranger = await make_user(db_session, phone="+224620009981", role=UserRole.BUYER)
    assert (await client.get(url, headers=auth_headers(stranger))).status_code == 403
    other_key = f"/pickup-point-applications/{saved['id']}/documents/{_key()}"
    assert (await client.get(other_key, headers=auth_headers(admin_user))).status_code == 404
