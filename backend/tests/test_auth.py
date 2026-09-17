"""Tests for registration, login, refresh, forgot/reset password and
role-protected routes."""

import re

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.users.models import User
from tests.conftest import auth_headers

ADMIN_BOOTSTRAP_PAYLOAD = {"phone": "+224629999999", "password": "password123", "email": "admin@example.com"}

REGISTER_PAYLOAD = {"phone": "+224621111111", "password": "password123", "email": "buyer@example.com"}


def _stub_send_email(monkeypatch: pytest.MonkeyPatch, target: str) -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
        calls.append((to, subject, body))

    monkeypatch.setattr(target, fake_send_email)
    return calls


async def test_register_creates_buyer_account(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "buyer"
    assert me.json()["phone"] == REGISTER_PAYLOAD["phone"]


async def test_register_rejects_duplicate_phone(client: AsyncClient) -> None:
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 409
    assert response.json()["detail"] == "Ce numéro de téléphone est déjà utilisé."


async def test_register_rejects_invalid_phone_format(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={"phone": "0621111111", "password": "password123"})

    assert response.status_code == 422


async def test_login_success(client: AsyncClient) -> None:
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    response = await client.post(
        "/auth/login", json={"phone": REGISTER_PAYLOAD["phone"], "password": REGISTER_PAYLOAD["password"]}
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_login_wrong_password_returns_generic_error(client: AsyncClient) -> None:
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    response = await client.post(
        "/auth/login", json={"phone": REGISTER_PAYLOAD["phone"], "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Numéro de téléphone ou mot de passe incorrect."


async def test_refresh_issues_new_token_pair(client: AsyncClient) -> None:
    register_response = await client.post("/auth/register", json=REGISTER_PAYLOAD)
    refresh_token = register_response.json()["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_refresh_rejects_access_token(client: AsyncClient) -> None:
    register_response = await client.post("/auth/register", json=REGISTER_PAYLOAD)
    access_token = register_response.json()["access_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/users/me")

    assert response.status_code == 401


async def test_role_protected_route_rejects_wrong_role(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User
) -> None:
    response = await client.post(
        "/categories", json={"name": "Mode"}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 403


async def test_role_protected_route_allows_admin(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    response = await client.post(
        "/categories", json={"name": "Mode"}, headers=auth_headers(admin_user)
    )

    assert response.status_code == 201


async def test_register_sends_verification_code(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_send_email(monkeypatch, "app.users.service.send_email")

    response = await client.post("/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    assert len(calls) == 1
    to, _subject, _body = calls[0]
    assert to == "buyer@example.com"


async def test_register_without_email_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"phone": REGISTER_PAYLOAD["phone"], "password": REGISTER_PAYLOAD["password"]}
    )

    assert response.status_code == 422


async def test_forgot_password_sends_code_when_email_on_file(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_send_email(monkeypatch, "app.auth.service.send_email")
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    response = await client.post("/auth/forgot-password", json={"phone": REGISTER_PAYLOAD["phone"]})

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == "buyer@example.com"


async def test_forgot_password_is_silent_for_unknown_phone(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_send_email(monkeypatch, "app.auth.service.send_email")

    response = await client.post("/auth/forgot-password", json={"phone": "+224699999999"})

    assert response.status_code == 200
    assert calls == []


async def test_reset_password_with_valid_code_allows_login(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_send_email(monkeypatch, "app.auth.service.send_email")
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    await client.post("/auth/forgot-password", json={"phone": REGISTER_PAYLOAD["phone"]})

    code = re.search(r"\d{5}", calls[0][2]).group()

    response = await client.post(
        "/auth/reset-password",
        json={"phone": REGISTER_PAYLOAD["phone"], "code": code, "new_password": "new-password123"},
    )
    assert response.status_code == 200

    login = await client.post(
        "/auth/login", json={"phone": REGISTER_PAYLOAD["phone"], "password": "new-password123"}
    )
    assert login.status_code == 200

    old_password_login = await client.post(
        "/auth/login", json={"phone": REGISTER_PAYLOAD["phone"], "password": REGISTER_PAYLOAD["password"]}
    )
    assert old_password_login.status_code == 401


async def test_reset_password_rejects_wrong_code(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_send_email(monkeypatch, "app.auth.service.send_email")
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    await client.post("/auth/forgot-password", json={"phone": REGISTER_PAYLOAD["phone"]})

    response = await client.post(
        "/auth/reset-password",
        json={"phone": REGISTER_PAYLOAD["phone"], "code": "00000", "new_password": "new-password123"},
    )

    assert response.status_code == 409


async def test_reset_password_rejects_unknown_phone(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/reset-password",
        json={"phone": "+224699999999", "code": "12345", "new_password": "new-password123"},
    )

    assert response.status_code == 409


async def test_admin_bootstrap_creates_admin_account(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "admin_bootstrap_token", "test-secret")

    response = await client.post(
        "/auth/admin-bootstrap",
        headers={"x-bootstrap-token": "test-secret"},
        json=ADMIN_BOOTSTRAP_PAYLOAD,
    )
    assert response.status_code == 201

    login = await client.post(
        "/auth/login",
        json={"phone": ADMIN_BOOTSTRAP_PAYLOAD["phone"], "password": ADMIN_BOOTSTRAP_PAYLOAD["password"]},
    )
    assert login.status_code == 200

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["role"] == "admin"
    assert me.json()["email_verified"] is True


async def test_admin_bootstrap_rejects_wrong_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "admin_bootstrap_token", "test-secret")

    response = await client.post(
        "/auth/admin-bootstrap",
        headers={"x-bootstrap-token": "wrong-token"},
        json=ADMIN_BOOTSTRAP_PAYLOAD,
    )

    assert response.status_code == 403


async def test_admin_bootstrap_rejects_when_not_configured(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "admin_bootstrap_token", None)

    response = await client.post(
        "/auth/admin-bootstrap",
        headers={"x-bootstrap-token": "anything"},
        json=ADMIN_BOOTSTRAP_PAYLOAD,
    )

    assert response.status_code == 403


async def test_admin_bootstrap_rejects_once_an_admin_exists(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "admin_bootstrap_token", "test-secret")

    response = await client.post(
        "/auth/admin-bootstrap",
        headers={"x-bootstrap-token": "test-secret"},
        json=ADMIN_BOOTSTRAP_PAYLOAD,
    )

    assert response.status_code == 409
