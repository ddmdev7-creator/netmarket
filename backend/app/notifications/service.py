"""Order notifications: an in-app entry (persisted + pushed live over
WebSocket, see ws_manager.py) plus, for the two status changes that mean
"go get your package" (arrival at a pickup point, or delivery at home), an
email to the buyer — both best-effort side effects of the action that
triggered them (placing an order, a vendor/courier/pickup point manager
moving a sub-order forward).

Email is intentionally NOT sent for every status change (confirmed,
preparing, shipped, cancelled) — the in-app + WebSocket channel already
covers those in real time, and mailing on every hop was pure volume with no
buyer action attached to it. Only the two "package has physically arrived
somewhere the buyer needs to act on" transitions justify the extra channel.

SMS is on the roadmap (cahier des charges §4.1) but no SMS gateway is
integrated yet — there is no provider account for the Guinean market at
time of writing, and phone is the one field every account is guaranteed to
have (email is optional at buyer signup, see app/auth/service.py), so email
alone won't reach every buyer. The in-app channel doesn't have that gap —
every account can see its own notification feed — so it's the primary
channel now; email is a secondary nudge, silently skipped when the buyer
has no email on file.
"""

import logging
import smtplib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.notifications import repository
from app.notifications.models import Notification, NotificationType
from app.notifications.ws_manager import manager as ws_manager
from app.orders.models import DeliveryType, OrderStatus, SubOrder
from app.users.models import User

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    OrderStatus.CONFIRMED: "confirmée",
    OrderStatus.PREPARING: "en préparation",
    OrderStatus.SHIPPED: "expédiée",
    OrderStatus.ARRIVED_AT_PICKUP_POINT: "arrivée à votre point de retrait",
    OrderStatus.DELIVERED: "livrée",
    OrderStatus.CANCELLED: "annulée",
}


async def _persist_and_push(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    type_: NotificationType,
    title: str,
    body: str,
    order_id: uuid.UUID | None,
    sub_order_id: uuid.UUID | None = None,
) -> Notification:
    notification = await repository.create(
        db, user_id=user_id, type=type_, title=title, body=body, order_id=order_id, sub_order_id=sub_order_id
    )
    await db.commit()
    await db.refresh(notification)
    try:
        await ws_manager.send_to_user(
            user_id,
            {
                "id": str(notification.id),
                "type": notification.type.value,
                "title": notification.title,
                "body": notification.body,
                "order_id": str(notification.order_id) if notification.order_id else None,
                "sub_order_id": str(notification.sub_order_id) if notification.sub_order_id else None,
                "read_at": None,
                "created_at": notification.created_at.isoformat(),
            },
        )
    except Exception:  # noqa: BLE001 - la notification est déjà persistée, un échec de push ne doit rien annuler
        logger.warning("Échec de push WebSocket pour la notification %s", notification.id, exc_info=True)
    return notification


async def notify_order_received(
    db: AsyncSession, *, vendor_user_id: uuid.UUID, shop_name: str, order_id: uuid.UUID, item_count: int, amount: int
) -> None:
    formatted_amount = f"{amount:,}".replace(",", " ")
    await _persist_and_push(
        db,
        user_id=vendor_user_id,
        type_=NotificationType.ORDER_RECEIVED,
        title="Nouvelle commande reçue",
        body=(
            f"Vous avez reçu une nouvelle commande pour « {shop_name} » "
            f"({item_count} article(s), {formatted_amount} GNF)."
        ),
        order_id=order_id,
    )


async def notify_sub_order_status_changed(db: AsyncSession, buyer: User, sub_order: SubOrder) -> None:
    label = _STATUS_LABELS.get(sub_order.status)
    if label is None:
        return

    await _persist_and_push(
        db,
        user_id=buyer.id,
        type_=NotificationType.ORDER_STATUS_CHANGED,
        title=f"Commande {label}",
        body=f"Votre commande chez « {sub_order.shop_name} » est maintenant {label}.",
        order_id=sub_order.order_id,
    )

    is_home_delivery_arrival = (
        sub_order.status == OrderStatus.DELIVERED and sub_order.order.delivery_type == DeliveryType.HOME_DELIVERY
    )
    if sub_order.status != OrderStatus.ARRIVED_AT_PICKUP_POINT and not is_home_delivery_arrival:
        return

    if not buyer.email:
        return
    try:
        await send_email(
            buyer.email,
            f"Votre commande chez {sub_order.shop_name} est {label}",
            f"Bonjour,\n\nVotre commande chez « {sub_order.shop_name} » est maintenant {label}.\n\n"
            "Vous pouvez suivre son statut dans votre espace « Mes commandes ».",
        )
    except (OSError, smtplib.SMTPException):
        logger.warning("Échec d'envoi de la notification de statut pour la sous-commande %s", sub_order.id)


async def notify_courier_verification_approved(db: AsyncSession, *, courier_user_id: uuid.UUID) -> None:
    await _persist_and_push(
        db,
        user_id=courier_user_id,
        type_=NotificationType.COURIER_VERIFICATION_APPROVED,
        title="Vérification approuvée",
        body="Votre inscription en tant que livreur a été validée. Vous pouvez maintenant recevoir des livraisons.",
        order_id=None,
    )


async def notify_courier_verification_rejected(db: AsyncSession, *, courier_user_id: uuid.UUID, admin_note: str) -> None:
    await _persist_and_push(
        db,
        user_id=courier_user_id,
        type_=NotificationType.COURIER_VERIFICATION_REJECTED,
        title="Vérification refusée",
        body=f"Votre inscription en tant que livreur a été refusée. Motif : {admin_note}",
        order_id=None,
    )


async def notify_delivery_request(
    db: AsyncSession,
    *,
    courier_user_id: uuid.UUID,
    sub_order_id: uuid.UUID,
    shop_name: str,
    amount: int,
    distance_km: float,
) -> None:
    formatted_amount = f"{amount:,}".replace(",", " ")
    await _persist_and_push(
        db,
        user_id=courier_user_id,
        type_=NotificationType.DELIVERY_REQUEST,
        title="Nouvelle demande de livraison",
        body=(
            f"« {shop_name} » recherche un livreur — {formatted_amount} GNF, "
            f"à environ {distance_km:.1f} km de vous."
        ),
        order_id=None,
        sub_order_id=sub_order_id,
    )


async def notify_delivery_request_accepted(
    db: AsyncSession, *, vendor_user_id: uuid.UUID, sub_order_id: uuid.UUID, courier_name: str
) -> None:
    await _persist_and_push(
        db,
        user_id=vendor_user_id,
        type_=NotificationType.DELIVERY_REQUEST_ACCEPTED,
        title="Livreur trouvé",
        body=f"{courier_name} a accepté de livrer cette commande.",
        order_id=None,
        sub_order_id=sub_order_id,
    )


async def notify_delivery_no_courier_found(db: AsyncSession, *, vendor_user_id: uuid.UUID, sub_order_id: uuid.UUID) -> None:
    await _persist_and_push(
        db,
        user_id=vendor_user_id,
        type_=NotificationType.DELIVERY_NO_COURIER_FOUND,
        title="Aucun livreur n'a répondu",
        body="Aucun livreur disponible n'a accepté cette livraison — réessaie ou assigne un livreur manuellement.",
        order_id=None,
        sub_order_id=sub_order_id,
    )
