"""Public webhook endpoint for Djomy (no auth dependency — Djomy calls this
directly, not a logged-in user; the HMAC signature is the authentication).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.payments import djomy_client, service

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)


@router.post("/webhooks/djomy")
async def djomy_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    raw_body = await request.body()
    if not djomy_client.verify_webhook_signature(raw_body, request.headers.get("X-Webhook-Signature")):
        logger.warning("Webhook Djomy rejeté : signature invalide ou absente.")
        return Response(status_code=400)

    payload = await request.json()
    data = payload.get("data") or {}
    # V2 : payout imbriqué sous data.payout — rien à faire tant que le module
    # de remboursement/versement n'existe pas (voir app/payments/service.py).
    if "payout" in data:
        return Response(status_code=200)
    # V1 : les champs du paiement sont directement dans `data`. V2 : imbriqués
    # sous `data.payment`.
    payment_data = data.get("payment", data)

    reference = payment_data.get("merchantPaymentReference")
    order_id: uuid.UUID | None = None
    if reference:
        try:
            order_id = uuid.UUID(reference)
        except ValueError:
            order_id = None
    if order_id is None:
        logger.warning("Webhook Djomy sans référence de commande exploitable : %r", reference)
        return Response(status_code=200)

    await service.apply_djomy_event(db, event_type=payload.get("eventType", ""), order_id=order_id)
    return Response(status_code=200)
