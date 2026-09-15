"""Checkout (cart → order split by vendor), order tracking and sub-order status transitions."""

import asyncio
import logging
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart import repository as cart_repository
from app.common.delivery_estimate import estimate_delivery_window
from app.common.geo import haversine_km
from app.catalog import repository as catalog_repository
from app.catalog.models import ProductStatus
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import InvalidTokenError, TokenType, create_delivery_token, decode_token
from app.couriers import repository as courier_repository
from app.couriers.models import CourierStatus
from app.notifications import service as notifications_service
from app.orders import repository
from app.orders.models import DeliveryType, Order, OrderStatus, SubOrder
from app.orders.schemas import CheckoutRequest, CourierAssignRequest, DispatchRequest, SubOrderStatusUpdate
from app.payments import repository as payments_repository
from app.payments import service as payments_service
from app.payments.models import PaymentStatus
from app.pickup_point_managers import repository as pickup_point_manager_repository
from app.pickup_points import repository as pickup_points_repository
from app.users import repository as user_repository
from app.users.models import User, UserRole
from app.vendors import repository as vendor_repository

logger = logging.getLogger(__name__)

# Délai laissé à chaque livreur candidat pour répondre à une offre avant de
# passer au suivant (voir start_dispatch/_run_dispatch). En mémoire du
# process, pas persisté — même choix que ws_manager (mono-instance, cf.
# plan) : un redémarrage de l'API pendant une recherche perd le minuteur, la
# sous-commande reste juste sans livreur (le vendeur peut relancer ou
# assigner manuellement).
OFFER_TIMEOUT_SECONDS = 45
_dispatch_events: dict[uuid.UUID, asyncio.Event] = {}

# Transitions autorisées, pilotées par le vendeur (accepter, préparer, expédier, livrer)
# ou par annulation (avant expédition uniquement). SHIPPED n'a pas d'entrée
# fixe ici : sa cible dépend du delivery_type (voir _allowed_next_statuses).
_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.SHIPPED},
    OrderStatus.SHIPPED: set(),
    OrderStatus.ARRIVED_AT_PICKUP_POINT: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

_STATUS_RANK = {
    OrderStatus.PENDING: 0,
    OrderStatus.CONFIRMED: 1,
    OrderStatus.PREPARING: 2,
    OrderStatus.SHIPPED: 3,
    OrderStatus.ARRIVED_AT_PICKUP_POINT: 4,
    OrderStatus.DELIVERED: 5,
}


def _allowed_next_statuses(current: OrderStatus, delivery_type: DeliveryType) -> set[OrderStatus]:
    """Delivery-type-aware transition lookup. Only the SHIPPED node branches:
    a home_delivery sub-order goes straight to DELIVERED (buyer's QR scanned
    by courier/vendor, unchanged flow) ; a pickup_point one must pass through
    ARRIVED_AT_PICKUP_POINT first (courier's QR scanned by the point
    manager), then DELIVERED (buyer's QR scanned by the point manager).
    Every other status uses the flat _ALLOWED_TRANSITIONS table unchanged."""
    if current == OrderStatus.SHIPPED:
        if delivery_type == DeliveryType.PICKUP_POINT:
            return {OrderStatus.ARRIVED_AT_PICKUP_POINT}
        return {OrderStatus.DELIVERED}
    return _ALLOWED_TRANSITIONS.get(current, set())


def _compute_order_status(sub_orders: list[SubOrder]) -> OrderStatus:
    active = [so for so in sub_orders if so.status != OrderStatus.CANCELLED]
    if not active:
        return OrderStatus.CANCELLED
    return min(active, key=lambda so: _STATUS_RANK[so.status]).status


def _commission_amount(amount: int, commission_rate: Decimal) -> int:
    return int((Decimal(amount) * commission_rate / Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))


def _attach_payment_status(order: Order, payment_status: PaymentStatus | None) -> Order:
    # Same transient-attribute pattern as delivery_token below: payment_status
    # isn't an Order column, it lives on the separate Payment row (app/payments/).
    order.payment_status = payment_status
    return order


def _attach_delivery_tokens(order: Order) -> Order:
    # Mirrors _attach_delivery_address below: delivery_token isn't a SubOrder
    # column, it's minted on read. It's the buyer's own turn to be scanned —
    # and so this only gets minted — at "shipped" for home_delivery (courier
    # scans it, unchanged flow) or at "arrived_at_pickup_point" for
    # pickup_point (the point manager scans it once the parcel is on-site).
    # A pickup_point sub-order at "shipped" deliberately gets nothing here:
    # that's the courier→point drop-off stage, the buyer isn't involved yet
    # (see _attach_pickup_dropoff_token for the courier's own code at that
    # stage). Anything else keeps the buyer's order screen from showing a
    # scan code that can't do anything.
    for sub_order in order.sub_orders:
        is_buyers_turn = (
            sub_order.status == OrderStatus.SHIPPED and order.delivery_type == DeliveryType.HOME_DELIVERY
        ) or (
            sub_order.status == OrderStatus.ARRIVED_AT_PICKUP_POINT
            and order.delivery_type == DeliveryType.PICKUP_POINT
        )
        sub_order.delivery_token = create_delivery_token(str(sub_order.id)) if is_buyers_turn else None
    return order


async def checkout_cart(db: AsyncSession, user: User, data: CheckoutRequest) -> Order:
    rows = await cart_repository.list_items_with_product_and_vendor(db, user.id)
    if not rows:
        raise ConflictError("Votre panier est vide.")

    for cart_item, product, _vendor in rows:
        if product.status != ProductStatus.ACTIVE:
            raise ConflictError(f"Le produit « {product.name} » n'est plus disponible.")
        if product.stock < cart_item.quantity:
            raise ConflictError(f"Stock insuffisant pour « {product.name} » (disponible : {product.stock}).")

    by_vendor: dict[uuid.UUID, list[tuple]] = {}
    for row in rows:
        by_vendor.setdefault(row[2].id, []).append(row)

    grand_total = sum(product.price * cart_item.quantity for cart_item, product, _ in rows)

    pickup_point_id = None
    if data.delivery_type == DeliveryType.PICKUP_POINT:
        if data.pickup_point_id is None:
            raise ConflictError("Un point de retrait doit être sélectionné.")
        point = await pickup_points_repository.get_by_id(db, data.pickup_point_id)
        if point is None or not point.is_active:
            raise ConflictError("Ce point de retrait n'est pas disponible.")
        pickup_point_id = data.pickup_point_id

    # Un point de retrait n'a pas de destinataire personnel (voir
    # AddressForm.vue côté frontend, qui vide déjà ces champs) — on l'impose
    # aussi ici plutôt que de faire confiance uniquement au client.
    is_pickup = data.delivery_type == DeliveryType.PICKUP_POINT
    order = await repository.create_order(
        db,
        user_id=user.id,
        delivery_address=data.delivery_address,
        delivery_type=data.delivery_type,
        payment_method=data.payment_method,
        total=grand_total,
        pickup_point_id=pickup_point_id,
        delivery_zone=data.delivery_zone,
        delivery_instructions=data.delivery_instructions,
        recipient_name=None if is_pickup else data.recipient_name,
        recipient_phone=None if is_pickup else data.recipient_phone,
    )
    await payments_service.create_payment_for_order(db, order)

    # Capturé ici (plutôt que relu après coup) pour notifier chaque vendeur
    # une fois la commande commitée, sans dépendre d'objets déjà chargés
    # avant le commit — voir la boucle de notification plus bas.
    vendor_notifications: list[tuple[uuid.UUID, str, int, int]] = []

    for vendor_items in by_vendor.values():
        vendor = vendor_items[0][2]
        amount = sum(product.price * cart_item.quantity for cart_item, product, _ in vendor_items)
        commission = _commission_amount(amount, Decimal(str(vendor.commission_rate)))
        # Figée au checkout — voir le commentaire sur SubOrder.estimated_delivery_min
        # dans app/orders/models.py pour pourquoi ce n'est pas recalculé à la volée.
        estimate = estimate_delivery_window(
            vendor_zone=vendor.zone,
            buyer_zone=data.delivery_zone,
            preparation_days=vendor.preparation_days,
            from_date=date.today(),
        )

        sub_order = await repository.create_sub_order(
            db,
            order_id=order.id,
            vendor_id=vendor.id,
            amount=amount,
            commission=commission,
            shop_name=vendor.shop_name,
            estimated_delivery_min=estimate.min_date,
            estimated_delivery_max=estimate.max_date,
        )

        for cart_item, product, _ in vendor_items:
            await repository.create_order_item(
                db,
                sub_order_id=sub_order.id,
                product_id=product.id,
                product_name=product.name,
                quantity=cart_item.quantity,
                unit_price=product.price,
            )
            product.stock -= cart_item.quantity

        vendor_notifications.append((vendor.user_id, vendor.shop_name, len(vendor_items), amount))

    await cart_repository.clear_for_user(db, user.id)
    await db.commit()

    for vendor_user_id, shop_name, item_count, amount in vendor_notifications:
        await notifications_service.notify_order_received(
            db, vendor_user_id=vendor_user_id, shop_name=shop_name, order_id=order.id, item_count=item_count, amount=amount
        )

    return await get_order(db, user, order.id)


async def get_order(db: AsyncSession, user: User, order_id: uuid.UUID) -> Order:
    order = await repository.get_order_by_id(db, order_id)
    if order is None or (order.user_id != user.id and user.role != UserRole.ADMIN):
        raise NotFoundError("Commande introuvable.")
    payment = await payments_repository.get_by_order_id(db, order.id)
    _attach_payment_status(order, payment.status if payment else None)
    await _attach_pickup_point_contacts(db, order, order.pickup_point_id)
    return _attach_delivery_tokens(order)


async def list_my_orders(db: AsyncSession, user: User) -> list[Order]:
    orders = await repository.list_orders_for_user(db, user.id)
    status_map = await payments_repository.get_status_map(db, [order.id for order in orders])
    for order in orders:
        _attach_payment_status(order, status_map.get(order.id))
        await _attach_pickup_point_contacts(db, order, order.pickup_point_id)
    return [_attach_delivery_tokens(order) for order in orders]


async def cancel_order(db: AsyncSession, user: User, order_id: uuid.UUID) -> Order:
    order = await get_order(db, user, order_id)

    if any(sub_order.status != OrderStatus.PENDING for sub_order in order.sub_orders):
        raise ConflictError(
            "Cette commande ne peut plus être annulée : un vendeur a déjà commencé à la traiter."
        )

    for sub_order in order.sub_orders:
        sub_order.status = OrderStatus.CANCELLED
        for item in sub_order.items:
            product = await catalog_repository.get_product_by_id(db, item.product_id)
            if product is not None:
                product.stock += item.quantity

    order.status = OrderStatus.CANCELLED
    await payments_service.mark_cancelled(db, order.id)
    await db.commit()
    return await get_order(db, user, order_id)


def _attach_delivery_address(sub_order: SubOrder) -> SubOrder:
    # SubOrderRead.delivery_address isn't a SubOrder column — it lives on the
    # parent Order (see models.py) — so it's copied onto the transient
    # attribute Pydantic reads via from_attributes, same pattern as
    # Product.vendor_shop_name in app/catalog/repository.py. Same for the
    # structured fields alongside it (delivery_zone/instructions/recipient_*)
    # — all frozen on Order, none of them SubOrder columns.
    sub_order.delivery_address = sub_order.order.delivery_address
    sub_order.delivery_type = sub_order.order.delivery_type
    sub_order.delivery_zone = sub_order.order.delivery_zone
    sub_order.delivery_instructions = sub_order.order.delivery_instructions
    sub_order.recipient_name = sub_order.order.recipient_name
    sub_order.recipient_phone = sub_order.order.recipient_phone
    return sub_order


async def _attach_courier_info(db: AsyncSession, sub_order: SubOrder) -> SubOrder:
    sub_order.courier_name = None
    sub_order.courier_phone = None
    if sub_order.courier_id is not None:
        courier = await courier_repository.get_by_id(db, sub_order.courier_id)
        if courier is not None:
            sub_order.courier_name = courier.full_name
            sub_order.courier_phone = courier.phone
    return sub_order


async def _attach_dispatch_offer_info(db: AsyncSession, sub_order: SubOrder) -> SubOrder:
    sub_order.dispatch_offered_courier_name = None
    if sub_order.dispatch_offered_courier_id is not None:
        courier = await courier_repository.get_by_id(db, sub_order.dispatch_offered_courier_id)
        if courier is not None:
            sub_order.dispatch_offered_courier_name = courier.full_name or courier.phone
    return sub_order


async def _attach_pickup_point_contacts(db: AsyncSession, target, pickup_point_id: uuid.UUID | None) -> None:
    # Live lookup, deliberately not frozen: a pickup point can have several
    # managers, and who's currently staffing it can change after the order
    # was placed — unlike delivery_address/recipient_*, there's no single
    # "the" contact to snapshot at checkout time.
    if pickup_point_id is None:
        target.pickup_point_contacts = []
        return
    managers = await pickup_point_manager_repository.list_by_pickup_point(db, pickup_point_id)
    target.pickup_point_contacts = [{"name": m.full_name, "phone": m.phone} for m in managers]


async def list_my_sub_orders(db: AsyncSession, user: User) -> list[SubOrder]:
    vendor = await vendor_repository.get_by_user_id(db, user.id)
    if vendor is None:
        raise NotFoundError("Vous n'avez pas de boutique.")
    sub_orders = await repository.list_sub_orders_for_vendor(db, vendor.id)
    for so in sub_orders:
        _attach_delivery_address(so)
        await _attach_courier_info(db, so)
        await _attach_dispatch_offer_info(db, so)
        await _attach_pickup_point_contacts(db, so, so.order.pickup_point_id)
    return sub_orders


async def assign_courier(
    db: AsyncSession, user: User, sub_order_id: uuid.UUID, data: CourierAssignRequest
) -> SubOrder:
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")

    vendor = await vendor_repository.get_by_id(db, sub_order.vendor_id)
    if vendor is None or vendor.user_id != user.id:
        raise ForbiddenError("Cette sous-commande ne fait pas partie de votre boutique.")

    if sub_order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        raise ConflictError("Cette sous-commande est déjà finalisée.")

    if data.courier_id is not None:
        courier = await courier_repository.get_by_id(db, data.courier_id)
        if courier is None or courier.status != CourierStatus.APPROVED:
            raise ConflictError("Ce livreur n'est pas disponible.")

    sub_order.courier_id = data.courier_id
    # Assignation manuelle : prime sur un dispatch automatique en cours (voir
    # start_dispatch) — on vide son état et on réveille sa tâche de fond
    # tout de suite plutôt que d'attendre qu'elle constate le courier_id posé
    # à son prochain réveil (jusqu'à OFFER_TIMEOUT_SECONDS plus tard).
    sub_order.dispatch_offered_courier_id = None
    sub_order.dispatch_queue = []
    await db.commit()
    _wake_dispatch(sub_order_id)

    updated = await repository.get_sub_order_by_id(db, sub_order_id)
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    await _attach_dispatch_offer_info(db, updated)
    return await _attach_courier_info(db, updated)


def _attach_pickup_dropoff_token(sub_order: SubOrder) -> SubOrder:
    # The courier's own QR for the drop-off leg of a pickup_point order — the
    # point manager scans it (see confirm_delivery_by_token) to confirm
    # receipt. Same minting mechanism as _attach_delivery_tokens (a signed
    # JWT keyed only on sub_order_id — there's nothing cryptographically
    # tying it to "courier" vs "buyer", it's the audience/stage that gives it
    # meaning), only ever shown while there's actually something for the
    # courier to hand off.
    sub_order.pickup_dropoff_token = (
        create_delivery_token(str(sub_order.id))
        if sub_order.status == OrderStatus.SHIPPED and sub_order.order.delivery_type == DeliveryType.PICKUP_POINT
        else None
    )
    return sub_order


async def list_my_deliveries(db: AsyncSession, user: User) -> list[SubOrder]:
    courier = await courier_repository.get_by_user_id(db, user.id)
    if courier is None:
        raise NotFoundError("Vous n'avez pas de profil livreur.")
    sub_orders = await repository.list_sub_orders_for_courier(db, courier.id)
    for so in sub_orders:
        _attach_pickup_dropoff_token(_attach_delivery_address(so))
        await _attach_pickup_point_contacts(db, so, so.order.pickup_point_id)
    return sub_orders


async def list_my_point_deliveries(db: AsyncSession, user: User) -> list[SubOrder]:
    manager = await pickup_point_manager_repository.get_by_user_id(db, user.id)
    if manager is None:
        raise NotFoundError("Vous n'avez pas de profil gestionnaire de point de retrait.")
    sub_orders = await repository.list_sub_orders_for_pickup_point(db, manager.pickup_point_id)
    result = []
    for so in sub_orders:
        _attach_delivery_address(so)
        await _attach_courier_info(db, so)
        result.append(so)
    return result


async def update_sub_order_status(
    db: AsyncSession, user: User, sub_order_id: uuid.UUID, data: SubOrderStatusUpdate
) -> SubOrder:
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")

    vendor = await vendor_repository.get_by_id(db, sub_order.vendor_id)
    is_owner_vendor = vendor is not None and vendor.user_id == user.id

    is_assigned_courier = False
    if not is_owner_vendor and sub_order.courier_id is not None:
        courier = await courier_repository.get_by_id(db, sub_order.courier_id)
        is_assigned_courier = courier is not None and courier.user_id == user.id

    is_assigned_point_manager = False
    if not is_owner_vendor and not is_assigned_courier and sub_order.order.pickup_point_id is not None:
        manager = await pickup_point_manager_repository.get_by_user_id(db, user.id)
        is_assigned_point_manager = (
            manager is not None and manager.pickup_point_id == sub_order.order.pickup_point_id
        )

    if not is_owner_vendor and not is_assigned_courier and not is_assigned_point_manager:
        raise ForbiddenError("Cette sous-commande ne fait pas partie de votre boutique.")
    # Le vendeur pilote tout ce qui se passe avant que le colis ne quitte sa
    # boutique (accepter, préparer, expédier, annuler) mais jamais sa
    # réception/remise ensuite — ce n'est pas lui qui a physiquement le colis
    # à ce stade, donc ni "arrivée au point" ni "remise au client" ne
    # devraient pouvoir venir de lui, quel que soit le mode de livraison.
    if is_owner_vendor and data.status in {OrderStatus.ARRIVED_AT_PICKUP_POINT, OrderStatus.DELIVERED}:
        raise ForbiddenError(
            "Cette confirmation revient au livreur ou au gestionnaire du point de retrait, pas au vendeur."
        )
    # Le livreur assigné confirme la remise directe au client (livraison à
    # domicile). Pour un point de retrait, il n'a rien à confirmer lui-même :
    # il montre son propre QR (pickup_dropoff_token) et c'est le gestionnaire
    # qui le scanne — voir la branche is_assigned_point_manager ci-dessous.
    if is_assigned_courier:
        courier_allowed = (
            set() if sub_order.order.delivery_type == DeliveryType.PICKUP_POINT else {OrderStatus.DELIVERED}
        )
        if data.status not in courier_allowed:
            raise ForbiddenError(
                "Un livreur confirme la remise au client pour une livraison à domicile ; pour un point de "
                "retrait, c'est le gestionnaire du point qui confirme la réception et la remise."
            )
    # Le gestionnaire du point confirme les deux étapes qui se passent chez
    # lui : la réception du colis (en scannant le code du livreur, ou
    # manuellement) puis la remise finale au client (en scannant le QR de
    # l'acheteur, ou manuellement) — jamais les étapes en amont (accepter,
    # préparer, expédier), qui restent au vendeur.
    if is_assigned_point_manager and data.status not in {
        OrderStatus.ARRIVED_AT_PICKUP_POINT,
        OrderStatus.DELIVERED,
    }:
        raise ForbiddenError("Un gestionnaire de point de retrait ne peut que confirmer la réception ou la remise.")

    if data.status not in _allowed_next_statuses(sub_order.status, sub_order.order.delivery_type):
        raise ConflictError(
            f"Transition de statut invalide : « {sub_order.status.value} » → « {data.status.value} »."
        )

    # Un colis ne peut pas être "en route" sans personne pour le transporter —
    # le vendeur doit assigner un livreur (voir assign_courier) avant de
    # pouvoir marquer une sous-commande comme expédiée.
    if data.status == OrderStatus.SHIPPED and sub_order.courier_id is None:
        raise ConflictError("Assignez un livreur avant de marquer cette commande comme expédiée.")

    if data.status == OrderStatus.CANCELLED:
        for item in sub_order.items:
            product = await catalog_repository.get_product_by_id(db, item.product_id)
            if product is not None:
                product.stock += item.quantity

    sub_order.status = data.status
    await db.flush()

    order = await repository.get_order_by_id(db, sub_order.order_id)
    order.status = _compute_order_status(order.sub_orders)
    if order.status == OrderStatus.DELIVERED:
        # Cash on delivery: money only actually changes hands once every
        # vendor in the order has delivered — see payments/provider.py.
        await payments_service.mark_paid(db, order.id)

    await db.commit()

    buyer = await user_repository.get_by_id(db, order.user_id)
    if buyer is not None:
        await notifications_service.notify_sub_order_status_changed(db, buyer, sub_order)

    updated = await repository.get_sub_order_by_id(db, sub_order_id)
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    return await _attach_courier_info(db, updated)


async def confirm_delivery_by_token(db: AsyncSession, user: User, token: str) -> SubOrder:
    """Assigned courier or assigned pickup point manager scans a QR code (the
    buyer's, or — for a pickup_point order's first leg — the courier's own
    drop-off code, scanned by the manager) — decode it into a sub-order id,
    work out the single legal next status for its current (status,
    delivery_type), and run it through the exact same status-transition path
    (and its ownership check) as the manual status-update button, so a
    forged/reused/off-stage token fails the same way a bad manual transition
    would.

    home_delivery: shipped → delivered (buyer's QR, courier scans).
    pickup_point: shipped → arrived_at_pickup_point (courier's QR, manager
    scans) then arrived_at_pickup_point → delivered (buyer's QR, manager
    scans)."""
    try:
        payload = decode_token(token, TokenType.DELIVERY)
        sub_order_id = uuid.UUID(payload["sub"])
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise ConflictError("QR code invalide ou expiré.") from exc

    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise ConflictError("QR code invalide ou expiré.")

    next_statuses = _allowed_next_statuses(sub_order.status, sub_order.order.delivery_type)
    if len(next_statuses) != 1:
        # Rien à scanner à cet état (déjà livrée, annulée, pas encore
        # expédiée...) — même message que pour un jeton mal formé/expiré.
        raise ConflictError("QR code invalide ou expiré.")
    next_status = next(iter(next_statuses))

    return await update_sub_order_status(db, user, sub_order_id, SubOrderStatusUpdate(status=next_status))


def _wake_dispatch(sub_order_id: uuid.UUID) -> None:
    event = _dispatch_events.get(sub_order_id)
    if event is not None:
        event.set()


async def start_dispatch(db: AsyncSession, user: User, sub_order_id: uuid.UUID, data: DispatchRequest) -> SubOrder:
    """Offre la livraison au livreur en ligne le plus proche de la boutique,
    puis au suivant par distance croissante s'il refuse ou ne répond pas
    dans OFFER_TIMEOUT_SECONDS (voir _run_dispatch) — jamais une diffusion à
    tous où le premier à répondre l'emporterait, même s'il est plus loin
    qu'un autre candidat encore en train de regarder son téléphone."""
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")

    vendor = await vendor_repository.get_by_id(db, sub_order.vendor_id)
    if vendor is None or vendor.user_id != user.id:
        raise ForbiddenError("Cette sous-commande ne fait pas partie de votre boutique.")
    if sub_order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        raise ConflictError("Cette sous-commande est déjà finalisée.")
    if sub_order.courier_id is not None:
        raise ConflictError("Un livreur est déjà assigné à cette sous-commande.")
    if vendor.latitude is None or vendor.longitude is None:
        raise ConflictError("Configurez la position de votre boutique avant de rechercher un livreur.")

    candidates = await courier_repository.list_online_candidates(db, data.vehicle_type)
    if not candidates:
        raise ConflictError("Aucun livreur disponible pour le moment.")

    ranked = sorted(
        candidates,
        key=lambda c: haversine_km(vendor.latitude, vendor.longitude, c.latitude, c.longitude),
    )
    queue = [c.id for c in ranked[1:]]
    first = ranked[0]

    sub_order.dispatch_offered_courier_id = first.id
    sub_order.dispatch_queue = queue
    await db.commit()

    await notifications_service.notify_delivery_request(
        db,
        courier_user_id=first.user_id,
        sub_order_id=sub_order.id,
        shop_name=sub_order.shop_name,
        amount=sub_order.amount,
        distance_km=haversine_km(vendor.latitude, vendor.longitude, first.latitude, first.longitude),
    )

    _dispatch_events[sub_order.id] = asyncio.Event()
    asyncio.create_task(_run_dispatch(sub_order.id, vendor.latitude, vendor.longitude))

    updated = await repository.get_sub_order_by_id(db, sub_order_id)
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    await _attach_dispatch_offer_info(db, updated)
    return await _attach_courier_info(db, updated)


async def _offer_next(db: AsyncSession, sub_order: SubOrder, vendor_lat: float, vendor_lng: float) -> bool:
    """Dépile le prochain candidat VALIDE (encore en ligne) de la file et lui
    envoie l'offre. Renvoie False si la file s'épuise sans trouver personne —
    un candidat passé hors ligne entre le classement initial et son tour est
    juste sauté, sans lui faire consommer un cycle d'attente complet."""
    queue = list(sub_order.dispatch_queue)
    while queue:
        next_id = queue.pop(0)
        courier = await courier_repository.get_by_id(db, next_id)
        sub_order.dispatch_queue = queue
        if courier is None or not courier.is_online or courier.latitude is None or courier.longitude is None:
            continue

        sub_order.dispatch_offered_courier_id = courier.id
        await db.commit()
        await notifications_service.notify_delivery_request(
            db,
            courier_user_id=courier.user_id,
            sub_order_id=sub_order.id,
            shop_name=sub_order.shop_name,
            amount=sub_order.amount,
            distance_km=haversine_km(vendor_lat, vendor_lng, courier.latitude, courier.longitude),
        )
        return True

    sub_order.dispatch_offered_courier_id = None
    sub_order.dispatch_queue = []
    await db.commit()
    return False


async def _run_dispatch(sub_order_id: uuid.UUID, vendor_lat: float, vendor_lng: float) -> None:
    """Tâche de fond démarrée par start_dispatch — attend soit un signal
    (accept_delivery/decline_delivery/assign_courier réveillent l'Event),
    soit l'expiration du délai, puis avance à l'offre suivante. Tourne hors
    du cycle requête/réponse : chaque itération ouvre sa propre session DB
    plutôt que de garder une connexion du pool bloquée pendant l'attente."""
    event = _dispatch_events.get(sub_order_id)
    if event is None:
        return
    try:
        while True:
            try:
                await asyncio.wait_for(event.wait(), timeout=OFFER_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                pass
            event.clear()

            async with AsyncSessionLocal() as db:
                sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
                if sub_order is None or sub_order.courier_id is not None:
                    return  # accepté (ou assigné manuellement) entre-temps

                found = await _offer_next(db, sub_order, vendor_lat, vendor_lng)
                if not found:
                    vendor = await vendor_repository.get_by_id(db, sub_order.vendor_id)
                    if vendor is not None:
                        await notifications_service.notify_delivery_no_courier_found(
                            db, vendor_user_id=vendor.user_id, sub_order_id=sub_order.id
                        )
                    return
    except Exception:  # noqa: BLE001 - tâche de fond : logguer plutôt que perdre l'erreur silencieusement
        logger.exception("Erreur dans la tâche de dispatch pour la sous-commande %s", sub_order_id)
    finally:
        _dispatch_events.pop(sub_order_id, None)


async def accept_delivery(db: AsyncSession, user: User, sub_order_id: uuid.UUID) -> SubOrder:
    courier = await courier_repository.get_by_user_id(db, user.id)
    if courier is None:
        raise NotFoundError("Vous n'avez pas de profil livreur.")

    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")
    if sub_order.courier_id is not None:
        raise ConflictError("Cette livraison a déjà été prise.")
    if sub_order.dispatch_offered_courier_id != courier.id:
        raise ForbiddenError("Cette offre ne vous est plus destinée.")

    sub_order.courier_id = courier.id
    sub_order.dispatch_offered_courier_id = None
    sub_order.dispatch_queue = []
    await db.commit()
    _wake_dispatch(sub_order_id)

    vendor = await vendor_repository.get_by_id(db, sub_order.vendor_id)
    if vendor is not None:
        await notifications_service.notify_delivery_request_accepted(
            db, vendor_user_id=vendor.user_id, sub_order_id=sub_order.id, courier_name=courier.full_name or courier.phone
        )

    updated = await repository.get_sub_order_by_id(db, sub_order_id)
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    return await _attach_courier_info(db, updated)


async def decline_delivery(db: AsyncSession, user: User, sub_order_id: uuid.UUID) -> None:
    courier = await courier_repository.get_by_user_id(db, user.id)
    if courier is None:
        raise NotFoundError("Vous n'avez pas de profil livreur.")

    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")
    if sub_order.dispatch_offered_courier_id != courier.id:
        raise ForbiddenError("Cette offre ne vous est plus destinée.")

    # N'avance pas la file nous-mêmes : on ne fait que réveiller _run_dispatch
    # (déjà responsable de "qui est le prochain"), pour garder un seul
    # endroit qui décide de la progression, identique au cas d'expiration du
    # délai.
    _wake_dispatch(sub_order_id)
