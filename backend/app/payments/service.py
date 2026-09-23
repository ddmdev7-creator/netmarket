"""Payment orchestration: pick a provider by the order's payment method, persist the result."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.orders import repository as orders_repository
from app.orders.models import Order, PaymentMethod
from app.payments import djomy_client, repository
from app.payments.models import Payment, PaymentSettings, PaymentStatus
from app.payments.provider import get_provider
from app.wallets import buyer_service
from app.wallets import service as wallets_service

logger = logging.getLogger(__name__)


async def create_payment_for_order(db: AsyncSession, order: Order, *, payer_phone: str) -> str | None:
    """Returns a redirect URL when the provider sends the buyer to a hosted
    payment page (Djomy); None for cash on delivery or the NdjouriBank balance."""
    if order.payment_method == PaymentMethod.WALLET:
        # Solde insuffisant → ConflictError, avant que quoi que ce soit ne soit commité.
        await buyer_service.pay_order(db, order)
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
# changent rien (on part déjà de PENDING). payment.refunded n'est pas listé :
# on ne passe jamais par un remboursement Djomy natif, voir initiate_refund.
_DJOMY_EVENT_TO_STATUS: dict[str, PaymentStatus] = {
    "payment.success": PaymentStatus.PAID,
    "payment.failed": PaymentStatus.FAILED,
    "payment.timeout": PaymentStatus.FAILED,
    "payment.cancelled": PaymentStatus.CANCELLED,
}

# Événements du webhook payout.* (voir initiate_refund) — reçus seulement en
# V2 (la doc Djomy précise que payout.* n'est jamais envoyé en V1).
_DJOMY_PAYOUT_EVENT_TO_STATUS: dict[str, PaymentStatus] = {
    "payout.success": PaymentStatus.REFUNDED,
    "payout.failed": PaymentStatus.REFUND_FAILED,
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
    if new_status == PaymentStatus.PAID:
        await _record_capture(db, order_id)
    await db.commit()
    return True


async def _record_capture(db: AsyncSession, order_id: uuid.UUID) -> None:
    """Paiement confirmé → trésorerie/séquestre du grand livre (app/wallets)."""
    order = await orders_repository.get_order_by_id(db, order_id)
    if order is not None:
        await wallets_service.record_payment_captured(db, order)


async def apply_djomy_payout_event(db: AsyncSession, *, event_type: str, payout_id: str) -> bool:
    """Applies one payout.* webhook event (a refund's outcome, see
    initiate_refund) to the matching Payment, found by refund_reference."""
    new_status = _DJOMY_PAYOUT_EVENT_TO_STATUS.get(event_type)
    if new_status is None:
        return True
    payment = await repository.get_by_refund_reference(db, payout_id)
    if payment is None:
        logger.warning("Webhook Djomy %s pour un remboursement inconnu (payoutId=%s)", event_type, payout_id)
        return False
    payment.status = new_status
    if new_status == PaymentStatus.REFUNDED:
        order = await orders_repository.get_order_by_id(db, payment.order_id)
        if order is not None:
            await wallets_service.record_refund_completed(db, order)
    await db.commit()
    return True


async def initiate_refund(db: AsyncSession, payment: Payment, *, order_reference: str, beneficiary_name: str) -> None:
    """Called from app/orders/service.py::cancel_order when an online
    payment is cancelled before any vendor started processing it. Djomy has
    no dedicated "reverse this transaction" endpoint — a refund is an
    outbound payout back to the payer's own mobile money account (see
    djomy_client.create_refund_payout). Does not commit — the caller
    (cancel_order) commits once alongside the rest of the cancellation.
    """
    if not payment.provider_reference:
        raise ConflictError("Remboursement impossible : aucune transaction Djomy associée à ce paiement.")

    transaction = await djomy_client.get_payment_status(payment.provider_reference)
    payer_number = transaction.get("payerIdentifier")
    provider_code = transaction.get("paymentMethod")
    paid_amount = transaction.get("paidAmount")
    if not payer_number or not provider_code or not paid_amount:
        raise ConflictError(
            "Remboursement impossible : détails de paiement Djomy incomplets — contacte le support."
        )

    payout_item_id = await djomy_client.create_refund_payout(
        amount=int(paid_amount),
        account_number=payer_number,
        provider_code=provider_code,
        beneficiary_name=beneficiary_name,
        reference=order_reference,
        message=f"Remboursement commande netmarket #{order_reference[:8].upper()}",
    )
    payment.status = PaymentStatus.REFUND_PENDING
    payment.refund_reference = payout_item_id


async def get_refund_settings(db: AsyncSession) -> PaymentSettings:
    return await repository.get_settings(db)


async def update_refund_delay(db: AsyncSession, refund_delay_hours: int) -> PaymentSettings:
    settings_row = await repository.get_settings(db)
    settings_row.refund_delay_hours = refund_delay_hours
    await db.commit()
    return settings_row


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
        if new_status == PaymentStatus.PAID:
            await _record_capture(db, order.id)
        await db.commit()
