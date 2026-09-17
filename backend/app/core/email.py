"""Outbound email — Brevo transactional API (https://api.brevo.com/v3/smtp/email).

Without BREVO_API_KEY set (local dev/CI without a Brevo account), the email
is logged instead of sent — no external account required to develop.
"""

import logging

import httpx

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


async def send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
    if not settings.brevo_api_key:
        logger.warning("BREVO_API_KEY absent — email non envoyé (to=%s, subject=%s)", to, subject)
        return

    payload = {
        "sender": {"name": settings.brevo_sender_name, "email": settings.brevo_sender_email},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    if html is not None:
        payload["htmlContent"] = html

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            BREVO_ENDPOINT,
            headers={"api-key": settings.brevo_api_key, "content-type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
