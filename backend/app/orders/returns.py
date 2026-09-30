"""Colis non retiré au point de retrait → retour au vendeur (décisions
métier 2026-09-30).

- Rappels à l'acheteur « votre colis vous attend » après REMINDER_DAYS jours,
  puis un dernier avertissement la veille du retour, avec le montant qu'il
  récupérera.
- Après PaymentSettings.pickup_storage_max_days jours au point, le colis
  passe « à retourner » (RETURN_PENDING) : le vendeur trouve un livreur
  (même recherche qu'à l'aller, depuis le point), qui présente son QR au
  gestionnaire (→ RETURNING) puis au vendeur, qui le scanne (→ RETURNED).
  Tant que le livreur n'est pas passé, l'acheteur peut encore retirer son colis.
- Argent (app/wallets/service.py::settle_return) : l'acheteur récupère les
  articles moins l'aller (y compris un retrait offert par le vendeur) et le
  retour ; les deux livreurs et le point (pickup_return_percent de son tarif)
  sont payés ; le vendeur ne perd rien et récupère son stock.
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.orders import handoff, repository
from app.orders.models import DeliveryType, Order, OrderStatus, PaymentMethod, SubOrder, SubOrderStatusEvent
from app.payments import repository as payments_repository
from app.payments.models import PaymentStatus
from app.users.models import User
from app.vendors.models import Vendor

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 30 * 60
REMINDER_DAYS = (3, 5)


def _gnf(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " GNF"


def estimated_refund(sub_order: SubOrder) -> int:
    """Articles − aller (y compris la part offerte par le vendeur) − retour (même course)."""
    return_fee = sub_order.return_fee or sub_order.effective_delivery_fee
    return max(0, sub_order.amount - (sub_order.vendor_delivery_fee or 0) - return_fee)


async def _is_paid(db: AsyncSession, order: Order) -> bool:
    if order.payment_method not in (PaymentMethod.ONLINE, PaymentMethod.WALLET):
        return False
    payment = await payments_repository.get_by_order_id(db, order.id)
    return payment is not None and payment.status == PaymentStatus.PAID


async def _waiting_parcels(db: AsyncSession) -> list[tuple[SubOrder, datetime]]:
    """Colis au point avec leur heure d'arrivée."""
    arrived = (
        select(SubOrderStatusEvent.sub_order_id, func.min(SubOrderStatusEvent.created_at).label("arrived_at"))
        .where(SubOrderStatusEvent.status == OrderStatus.ARRIVED_AT_PICKUP_POINT)
        .group_by(SubOrderStatusEvent.sub_order_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(SubOrder, arrived.c.arrived_at)
            .join(arrived, arrived.c.sub_order_id == SubOrder.id)
            .where(SubOrder.status == OrderStatus.ARRIVED_AT_PICKUP_POINT)
            .options(selectinload(SubOrder.order), selectinload(SubOrder.items))
        )
    ).all()
    return [(so, at) for so, at in rows]


async def start_return(db: AsyncSession, sub_order: SubOrder) -> None:
    """Le colis passe « à retourner » : le livreur de l'aller est gardé pour son
    paiement, la course retour est au prix de l'aller."""
    from app.notifications import service as notifications_service
    from app.orders.service import _compute_order_status, _signal_parcel_followers

    sub_order.outbound_courier_id = sub_order.courier_id
    sub_order.courier_id = None
    sub_order.dispatch_offered_courier_id = None
    sub_order.dispatch_queue = []
    sub_order.return_fee = sub_order.effective_delivery_fee
    sub_order.status = OrderStatus.RETURN_PENDING
    handoff.reset(sub_order)
    await db.flush()
    order = await repository.get_order_by_id(db, sub_order.order_id)
    order.status = _compute_order_status(order.sub_orders)
    await db.commit()

    vendor = await db.get(Vendor, sub_order.vendor_id)
    if vendor is not None:
        await notifications_service.notify_parcel_return(
            db,
            user=await db.get(User, vendor.user_id),
            title="Colis non retiré : organisez le retour",
            body=(
                f"Le client n'est pas venu chercher sa commande au point de retrait. Trouvez un livreur pour la "
                "rapporter : scannez son QR à la réception, les articles reviendront en stock. Le retour est à la "
                "charge du client, pas de la boutique."
            ),
            order_id=None,
            path="/vendeur/commandes",
        )
    buyer = await db.get(User, order.user_id)
    if buyer is not None:
        refund = (
            f" Vous serez remboursé de {_gnf(estimated_refund(sub_order))} sur NdjouriBank "
            "(articles, moins la livraison aller et le retour)."
            if await _is_paid(db, order)
            else ""
        )
        await notifications_service.notify_parcel_return(
            db,
            user=buyer,
            title="Votre colis retourne chez le vendeur",
            body=(
                f"Votre commande chez « {sub_order.shop_name} » n'a pas été retirée à temps et va être renvoyée à la "
                f"boutique. Vous pouvez encore la retirer au point tant que le livreur n'est pas passé.{refund}"
            ),
            order_id=order.id,
        )
    updated = await repository.get_sub_order_by_id(db, sub_order.id)
    await _signal_parcel_followers(db, updated)


async def _remind(db: AsyncSession, sub_order: SubOrder, days: int, max_days: int) -> None:
    from app.notifications import service as notifications_service

    order = sub_order.order
    buyer = await db.get(User, order.user_id)
    if buyer is None:
        return
    left = max_days - days
    if left <= 1:
        refund = (
            f" Sinon, il sera renvoyé à la boutique et vous serez remboursé de {_gnf(estimated_refund(sub_order))} "
            f"seulement (les frais de retour de {_gnf(sub_order.effective_delivery_fee)} et la livraison aller "
            "sont déduits)."
            if await _is_paid(db, order)
            else " Sinon, il sera renvoyé à la boutique."
        )
        title = "Dernier jour pour retirer votre colis"
        body = f"Votre commande chez « {sub_order.shop_name} » vous attend au point de retrait jusqu'à demain.{refund}"
    else:
        title = "Votre colis vous attend"
        body = (
            f"Votre commande chez « {sub_order.shop_name} » est au point de retrait depuis {days} jours. "
            f"Venez la retirer avec votre QR code : il vous reste {left} jours."
        )
    await notifications_service.notify_parcel_return(
        db, user=buyer, title=title, body=body, order_id=order.id, reminder=True
    )


async def run_once(db: AsyncSession, *, now: datetime | None = None) -> None:
    from app.wallets.service import _now

    now = now or _now()
    settings_row = await payments_repository.get_settings(db)
    max_days = settings_row.pickup_storage_max_days
    if max_days <= 0:
        return
    thresholds = sorted({d for d in REMINDER_DAYS if d < max_days - 1} | {max_days - 1} - {0})
    for sub_order, arrived_at in await _waiting_parcels(db):
        if sub_order.order.delivery_type != DeliveryType.PICKUP_POINT:
            continue
        days = math.floor((now - arrived_at) / timedelta(days=1))
        if days >= max_days:
            await start_return(db, sub_order)
            continue
        due = [t for t in thresholds if days >= t and (sub_order.pickup_reminder_days or 0) < t]
        if due:
            sub_order.pickup_reminder_days = max(due)
            await db.commit()
            await _remind(db, sub_order, days, max_days)


async def notify_returned(db: AsyncSession, buyer: User, order: Order, sub_order: SubOrder) -> None:
    from app.notifications import service as notifications_service

    refund = (
        f" {_gnf(estimated_refund(sub_order))} ont été crédités sur votre solde NdjouriBank."
        if await _is_paid(db, order)
        else ""
    )
    await notifications_service.notify_parcel_return(
        db,
        user=buyer,
        title="Colis rendu au vendeur",
        body=f"Votre commande chez « {sub_order.shop_name} », non retirée, est revenue à la boutique.{refund}",
        order_id=order.id,
    )


async def run_forever() -> None:
    while True:
        await asyncio.sleep(90)
        try:
            async with AsyncSessionLocal() as db:
                await run_once(db)
        except Exception:  # noqa: BLE001 - la boucle doit survivre à une erreur ponctuelle
            logger.exception("Échec de la tâche des retours de colis")
        await asyncio.sleep(INTERVAL_SECONDS - 90)
