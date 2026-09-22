"""Payment orchestration: pick a provider by the order's payment method, persist the result."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.orders.models import Order, PaymentMethod
from app.payments import djomy_client, repository
from app.payments.models import PaymentStatus
from app.payments.provider import get_provider

logger = logging.getLogger(__name__)


async def create_payment_for_order(db: AsyncSession, order: Order, *, payer_phone: str) -> str | None:
    """Returns a redirect URL when the provider sends the buyer to a hosted
    payment page (Djomy); None for cash on delivery."""
    provider = get_provider(order.payment_method)
    status, provider_reference, redirect_url = await provider.initiate(order, payer_phone=payer_phone)
    await repository.create(
        db, order_id=order.id, method=order.payment_method, status=status, provider_reference=provider_reference
    )
    return redirect_url


async def _set_status(db: AsyncSession, order_id: uuid.UUID, status: PaymentStatus) -> None:
    payment = await repository.get_by_order_id(db, order_id)
    if payment is not None:
        payment.status = status


async def mark_paid(db: AsyncSession, order_id: uuid.UUID) -> None:
    """Called once every sub-order of an order reaches "delivered" — for cash on
    delivery, that's the moment the money actually changed hands."""
    await _set_status(db, order_id, PaymentStatus.PAID)


async def mark_cancelled(db: AsyncSession, order_id: uuid.UUID) -> None:
    await _set_status(db, order_id, PaymentStatus.CANCELLED)


# Événements Djomy qui changent notre statut (voir POST /payments/webhooks/djomy
# et app/payments/djomy_client.py) ; payment.pending/created/redirected ne
# changent rien (on part déjà de PENDING), payment.refunded n'est pas encore
# géré (remboursement — hors scope tant que le module ledger/payout n'existe pas).
_DJOMY_EVENT_TO_STATUS: dict[str, PaymentStatus] = {
    "payment.success": PaymentStatus.PAID,
    "payment.failed": PaymentStatus.FAILED,
    "payment.timeout": PaymentStatus.FAILED,
    "payment.cancelled": PaymentStatus.CANCELLED,
}

# Mêmes statuts, lus depuis `data.status` plutôt que `eventType` — utilisé
# par sync_pending_payment (GET status, pas de webhook) où il n'y a pas
# d'eventType.
_DJOMY_DATA_STATUS_TO_STATUS: dict[str, PaymentStatus] = {
    "SUCCESS": PaymentStatus.PAID,
    "FAILED": PaymentStatus.FAILED,
    "CANCELLED": PaymentStatus.CANCELLED,
}


async def apply_djomy_event(db: AsyncSession, *, event_type: str, order_id: uuid.UUID) -> bool:
    """Applies one payment.* webhook event to the matching Payment. Returns
    whether a Payment row was found (the router 200s either way — Djomy
    would otherwise retry an event we simply can't/don't need to act on)."""
    new_status = _DJOMY_EVENT_TO_STATUS.get(event_type)
    if new_status is None:
        return True
    payment = await repository.get_by_order_id(db, order_id)
    if payment is None:
        logger.warning("Webhook Djomy %s pour une commande inconnue (order_id=%s)", event_type, order_id)
        return False
    payment.status = new_status
    await db.commit()
    return True


async def sync_pending_payment(db: AsyncSession, order: Order) -> None:
    """Fallback reconciliation for an online payment still PENDING — used
    when the buyer returns from Djomy's portal before the webhook (if any is
    configured) has reached us. No-op for cash on delivery or an already-
    settled payment."""
    if order.payment_method != PaymentMethod.ONLINE:
        return
    payment = await repository.get_by_order_id(db, order.id)
    if payment is None or payment.status != PaymentStatus.PENDING or not payment.provider_reference:
        return
    data = await djomy_client.get_payment_status(payment.provider_reference)
    new_status = _DJOMY_DATA_STATUS_TO_STATUS.get(data.get("status", ""))
    if new_status is not None:
        payment.status = new_status
        await db.commit()
