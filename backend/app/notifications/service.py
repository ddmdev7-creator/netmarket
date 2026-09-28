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
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.core.config import get_settings
from app.core.email_templates import cta_email, order_status_email
from app.notifications import repository
from app.notifications.models import Notification, NotificationType
from app.notifications.ws_manager import manager as ws_manager
from app.orders.models import DeliveryType, OrderStatus, SubOrder
from app.users.models import User

settings = get_settings()

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
    product_id: uuid.UUID | None = None,
) -> Notification:
    notification = await repository.create(
        db,
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        order_id=order_id,
        sub_order_id=sub_order_id,
        product_id=product_id,
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
                "product_id": str(notification.product_id) if notification.product_id else None,
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
        subject, text, html = order_status_email(sub_order.shop_name, label)
        await send_email(buyer.email, subject, text, html)
    except httpx.HTTPError:
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
    courier_earning: int,
    distance_km: float,
) -> None:
    # Jamais le prix des articles : seulement ce qui concerne le livreur (son
    # gain sur les frais de livraison, la distance). Le détail (adresse, point
    # de retrait) est lu à part — GET /orders/sub-orders/{id}/delivery-offer.
    formatted_earning = f"{courier_earning:,}".replace(",", " ")
    await _persist_and_push(
        db,
        user_id=courier_user_id,
        type_=NotificationType.DELIVERY_REQUEST,
        title="Nouvelle demande de livraison",
        body=(
            f"« {shop_name} » recherche un livreur — gain {formatted_earning} GNF, "
            f"boutique à environ {distance_km:.1f} km de vous."
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


async def notify_pickup_application(
    db: AsyncSession, *, user_id: uuid.UUID, type_: NotificationType, title: str, body: str
) -> None:
    """Étapes d'une candidature gestionnaire de point de retrait (invitation,
    soumission côté admin, décisions côté candidat)."""
    await _persist_and_push(db, user_id=user_id, type_=type_, title=title, body=body, order_id=None)


async def push_refresh(user_ids: set[uuid.UUID], scope: str) -> None:
    """Signal silencieux (non enregistré, jamais affiché) : « relis tes
    données ». Pour les écrans qui suivent des colis sans que chaque
    changement mérite une notification (espace livreur, point de retrait)."""
    for user_id in user_ids:
        try:
            await ws_manager.send_to_user(user_id, {"type": "refresh", "scope": scope})
        except Exception:  # noqa: BLE001 — un signal perdu est rattrapé par la relecture périodique
            logger.info("Signal de rafraîchissement non envoyé", exc_info=True)


def _gnf(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " GNF"


async def _email_if_verified(user: User, *, heading: str, paragraphs: list[str], cta_label: str, path: str) -> None:
    """Relances (favoris, panier) : par email seulement vers une adresse vérifiée."""
    if not user.email or not user.email_verified:
        return
    try:
        subject, text, html = cta_email(
            heading=heading, paragraphs=paragraphs, cta_label=cta_label, cta_url=f"{settings.frontend_url}{path}"
        )
        await send_email(user.email, subject, text, html)
    except httpx.HTTPError:
        logger.warning("Échec d'envoi de l'email de relance à l'utilisateur %s", user.id)


async def notify_favorite_price_drop(db: AsyncSession, *, user: User, product, old_price: int, new_price: int) -> None:
    body = f"« {product.name} » passe de {_gnf(old_price)} à {_gnf(new_price)}."
    await _persist_and_push(
        db,
        user_id=user.id,
        type_=NotificationType.FAVORITE_PRICE_DROP,
        title="Prix en baisse sur un favori",
        body=body,
        order_id=None,
        product_id=product.id,
    )
    await _email_if_verified(
        user,
        heading="Un de vos favoris baisse de prix",
        paragraphs=["Bonjour,", body, "Le stock est limité : ne tardez pas trop."],
        cta_label="Voir le produit",
        path=f"/produits/{product.id}",
    )


async def notify_favorite_back_in_stock(db: AsyncSession, *, user: User, product) -> None:
    body = f"« {product.name} » est de nouveau disponible."
    await _persist_and_push(
        db,
        user_id=user.id,
        type_=NotificationType.FAVORITE_BACK_IN_STOCK,
        title="De retour en stock",
        body=body,
        order_id=None,
        product_id=product.id,
    )
    await _email_if_verified(
        user,
        heading="Votre favori est de retour",
        paragraphs=["Bonjour,", body],
        cta_label="Voir le produit",
        path=f"/produits/{product.id}",
    )


async def notify_cart_reminder(db: AsyncSession, *, user: User, item_count: int) -> None:
    articles = f"{item_count} article{'s' if item_count > 1 else ''}"
    body = f"Vous avez laissé {articles} dans votre panier. Finalisez votre commande quand vous voulez."
    await _persist_and_push(
        db,
        user_id=user.id,
        type_=NotificationType.CART_REMINDER,
        title="Vos articles vous attendent",
        body=body,
        order_id=None,
    )
    await _email_if_verified(
        user,
        heading="Vos articles vous attendent",
        paragraphs=["Bonjour,", body],
        cta_label="Voir mon panier",
        path="/panier",
    )
