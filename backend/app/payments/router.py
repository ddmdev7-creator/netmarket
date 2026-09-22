"""Public webhook endpoint for Djomy (no auth dependency — Djomy calls this
directly, not a logged-in user; the HMAC signature is the authentication)
plus the admin-only refund delay setting (admin_router)."""

import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.payments import djomy_client, service
from app.payments.schemas import PaymentSettingsRead, PaymentSettingsUpdate
from app.users.models import UserRole

router = APIRouter(prefix="/payments", tags=["payments"])
admin_router = APIRouter(
    prefix="/admin/payment-settings", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)
logger = logging.getLogger(__name__)


@admin_router.get("", response_model=PaymentSettingsRead)
async def admin_get_payment_settings(db: AsyncSession = Depends(get_db)) -> PaymentSettingsRead:
    return await service.get_refund_settings(db)


@admin_router.patch("", response_model=PaymentSettingsRead)
async def admin_update_payment_settings(
    payload: PaymentSettingsUpdate, db: AsyncSession = Depends(get_db)
) -> PaymentSettingsRead:
    return await service.update_refund_delay(db, payload.refund_delay_hours)


@router.post("/webhooks/djomy")
async def djomy_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    raw_body = await request.body()
    if not djomy_client.verify_webhook_signature(raw_body, request.headers.get("X-Webhook-Signature")):
        logger.warning("Webhook Djomy rejeté : signature invalide ou absente.")
        return Response(status_code=400)

    payload = await request.json()
    data = payload.get("data") or {}
    event_type = payload.get("eventType", "")

    # V2 : payout imbriqué sous data.payout (remboursement, voir
    # service.initiate_refund) — jamais envoyé en V1 d'après la doc Djomy.
    if "payout" in data:
        payout_id = (data.get("payout") or {}).get("payoutId")
        if not payout_id:
            logger.warning("Webhook Djomy payout sans payoutId exploitable.")
            return Response(status_code=200)
        await service.apply_djomy_payout_event(db, event_type=event_type, payout_id=payout_id)
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

    await service.apply_djomy_event(db, event_type=event_type, order_id=order_id)
    return Response(status_code=200)
