"""HTTP client for the Djomy payment gateway (https://developers.djomy.africa).

Auth: every call needs an `X-API-KEY: <clientId>:<signature>` header, where
`signature = HMAC_SHA256(message=clientId, key=clientSecret)` hex-encoded
(see _sign below), plus a Bearer access token obtained from POST /v1/auth
(same X-API-KEY header, no body) — it expires after ~1h, cached here with a
safety margin rather than re-authenticating on every call.

Style mirrors app/core/email.py (the other outbound-HTTP-to-a-third-party
module in this app): module-level settings, log-and-skip when unconfigured,
`raise_for_status()` left to propagate rather than swallowed.
"""

import hashlib
import hmac
import logging
import time

import httpx

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Marge de sécurité avant l'expiration réelle du token (1h côté Djomy) pour
# ne jamais partir en requête avec un jeton sur le point d'expirer.
_TOKEN_REFRESH_MARGIN_SECONDS = 60

_cached_token: str | None = None
_cached_token_expires_at: float = 0.0


class DjomyNotConfiguredError(Exception):
    """Levée quand DJOMY_CLIENT_ID/DJOMY_CLIENT_SECRET ne sont pas définis."""


def _require_credentials() -> tuple[str, str]:
    if not settings.djomy_client_id or not settings.djomy_client_secret:
        raise DjomyNotConfiguredError("DJOMY_CLIENT_ID/DJOMY_CLIENT_SECRET absents.")
    return settings.djomy_client_id, settings.djomy_client_secret


def _sign(message: str, secret: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _api_key_header(client_id: str, client_secret: str) -> str:
    return f"{client_id}:{_sign(client_id, client_secret)}"


async def _get_access_token() -> str:
    global _cached_token, _cached_token_expires_at
    if _cached_token is not None and time.monotonic() < _cached_token_expires_at:
        return _cached_token

    client_id, client_secret = _require_credentials()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.djomy_base_url}/v1/auth",
            headers={"X-API-KEY": _api_key_header(client_id, client_secret)},
            json={},
        )
        response.raise_for_status()
        data = response.json()["data"]

    _cached_token = data["accessToken"]
    _cached_token_expires_at = time.monotonic() + data["expiresIn"] - _TOKEN_REFRESH_MARGIN_SECONDS
    return _cached_token


async def _authenticated_headers() -> dict[str, str]:
    client_id, client_secret = _require_credentials()
    token = await _get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "X-API-KEY": _api_key_header(client_id, client_secret),
    }


async def initiate_gateway_payment(
    *,
    amount: int,
    payer_number: str,
    reference: str,
    description: str,
    return_url: str,
    cancel_url: str | None = None,
) -> tuple[str, str]:
    """Starts a redirect-flow payment (POST /v1/payments/gateway — the only
    Djomy endpoint that allows every payment method, cards included).
    Returns (transactionId, redirectUrl) — the caller must send the buyer's
    browser to redirectUrl."""
    headers = await _authenticated_headers()
    payload = {
        "amount": amount,
        "countryCode": "GN",
        "payerNumber": payer_number,
        "merchantPaymentReference": reference,
        "description": description,
        "returnUrl": return_url,
    }
    if cancel_url:
        payload["cancelUrl"] = cancel_url

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.djomy_base_url}/v1/payments/gateway", headers=headers, json=payload
        )
        response.raise_for_status()
        data = response.json()["data"]

    return data["transactionId"], data["redirectUrl"]


async def get_payment_status(transaction_id: str) -> dict:
    """GET /v1/payments/{id}/status — the response's `data` dict includes at
    least `status`, `paidAmount`, `paymentMethod`, `payerIdentifier`."""
    headers = await _authenticated_headers()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{settings.djomy_base_url}/v1/payments/{transaction_id}/status", headers=headers
        )
        response.raise_for_status()
        return response.json()["data"]


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Webhooks are signed with the merchant's clientSecret (not the access
    token) — header format is `v1:<hex hmac-sha256 of the raw JSON body>`.
    Constant-time compare to avoid a timing side-channel."""
    if not signature_header or not settings.djomy_client_secret:
        return False
    _, _, signature = signature_header.partition(":")
    if not signature:
        return False
    expected = hmac.new(settings.djomy_client_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
