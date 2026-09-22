"""Unit tests for the Djomy HTTP client's pure logic (HMAC signing, webhook
signature verification) — no network, no DB. See app/payments/djomy_client.py.
"""

import hashlib
import hmac

from app.payments import djomy_client


def test_api_key_signature_matches_hmac_sha256_of_client_id() -> None:
    header = djomy_client._api_key_header("djomy-merchant-001", "topsecret")

    client_id, signature = header.split(":", 1)
    expected = hmac.new(b"topsecret", b"djomy-merchant-001", hashlib.sha256).hexdigest()
    assert client_id == "djomy-merchant-001"
    assert signature == expected


def test_verify_webhook_signature_accepts_a_valid_signature(monkeypatch) -> None:
    monkeypatch.setattr(djomy_client.settings, "djomy_client_secret", "topsecret")
    body = b'{"eventType":"payment.success"}'
    signature = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()

    assert djomy_client.verify_webhook_signature(body, f"v1:{signature}") is True


def test_verify_webhook_signature_rejects_a_tampered_body(monkeypatch) -> None:
    monkeypatch.setattr(djomy_client.settings, "djomy_client_secret", "topsecret")
    signature = hmac.new(b"topsecret", b'{"eventType":"payment.success"}', hashlib.sha256).hexdigest()

    assert djomy_client.verify_webhook_signature(b'{"eventType":"payment.failed"}', f"v1:{signature}") is False


def test_verify_webhook_signature_rejects_missing_header(monkeypatch) -> None:
    monkeypatch.setattr(djomy_client.settings, "djomy_client_secret", "topsecret")

    assert djomy_client.verify_webhook_signature(b"{}", None) is False
    assert djomy_client.verify_webhook_signature(b"{}", "") is False


def test_verify_webhook_signature_rejects_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(djomy_client.settings, "djomy_client_secret", None)

    assert djomy_client.verify_webhook_signature(b"{}", "v1:whatever") is False
