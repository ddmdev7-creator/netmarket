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
from app.couriers import repository as courier_repository
from app.couriers.models import CourierStatus
from app.delivery import repository as delivery_repository
from app.delivery.service import compute_fee, compute_transit_days
from app.notifications import service as notifications_service
from app.orders import repository
from app.orders import handoff
from app.orders.models import DeliveryType, Order, OrderStatus, PaymentMethod, SubOrder
from app.orders.schemas import (
    OrderCancelRequest,
    CheckoutRequest,
    CourierAssignRequest,
    DeliveryQuoteRead,
    DeliveryQuoteRequest,
    DeliveryQuoteVendorRead,
    DispatchRequest,
    SubOrderStatusUpdate,
)
from app.payments import repository as payments_repository
from app.payments import service as payments_service
from app.wallets import buyer_service
from app.wallets import service as wallets_service
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


def _line_unit_price(product, variant) -> int:
    # Surcharge de prix par variante (optionnelle) ; sinon le prix du produit.
    return variant.price if (variant is not None and variant.price is not None) else product.price


def _attach_payment_status(order: Order, payment_status: PaymentStatus | None) -> Order:
    # Same transient-attribute pattern as handoff_ready below: payment_status
    # isn't an Order column, it lives on the separate Payment row (app/payments/).
    order.payment_status = payment_status
    return order


def _is_buyers_turn(sub_order: SubOrder, delivery_type: DeliveryType) -> bool:
    """C'est à l'acheteur de présenter son QR : à « shipped » pour une
    livraison à domicile (le livreur scanne), à « arrived_at_pickup_point »
    pour un point de retrait (le gestionnaire scanne)."""
    return (sub_order.status == OrderStatus.SHIPPED and delivery_type == DeliveryType.HOME_DELIVERY) or (
        sub_order.status == OrderStatus.ARRIVED_AT_PICKUP_POINT and delivery_type == DeliveryType.PICKUP_POINT
    )


def _is_couriers_dropoff_turn(sub_order: SubOrder) -> bool:
    """Le livreur présente son QR « dépôt » au gestionnaire du point."""
    return sub_order.status == OrderStatus.SHIPPED and sub_order.order.delivery_type == DeliveryType.PICKUP_POINT


def _attach_handoff_flags(order: Order) -> Order:
    # handoff_ready n'est pas une colonne : indique seulement qu'un QR est à
    # afficher. Le code lui-même se demande à part (get_handoff_code).
    for sub_order in order.sub_orders:
        sub_order.handoff_ready = _is_buyers_turn(sub_order, order.delivery_type)
    return order


async def _load_checkout_rows(db: AsyncSession, user: User) -> list[tuple]:
    rows = await cart_repository.list_items_with_product_variant_and_vendor(db, user.id)
    if not rows:
        raise ConflictError("Votre panier est vide.")
    return rows


def _group_by_vendor(rows: list[tuple]) -> dict[uuid.UUID, list[tuple]]:
    by_vendor: dict[uuid.UUID, list[tuple]] = {}
    for row in rows:
        by_vendor.setdefault(row[3].id, []).append(row)
    return by_vendor


def _vendor_amount(vendor_items: list[tuple]) -> int:
    return sum(_line_unit_price(product, variant) * cart_item.quantity for cart_item, product, variant, _ in vendor_items)


async def _resolve_destination(
    db: AsyncSession, data: DeliveryQuoteRequest
) -> tuple[uuid.UUID | None, tuple[float | None, float | None]]:
    """Pickup point id (None for home delivery) and the GPS position parcels
    are delivered to — the point's own position for a pickup point, the
    buyer's submitted one for a home delivery."""
    if data.delivery_type != DeliveryType.PICKUP_POINT:
        return None, (data.latitude, data.longitude)
    if data.pickup_point_id is None:
        raise ConflictError("Un point de retrait doit être sélectionné.")
    point = await pickup_points_repository.get_by_id(db, data.pickup_point_id)
    if point is None or not point.is_active:
        raise ConflictError("Ce point de retrait n'est pas disponible.")
    return point.id, (point.latitude, point.longitude)


async def quote_delivery(db: AsyncSession, user: User, data: DeliveryQuoteRequest) -> DeliveryQuoteRead:
    """Delivery fee per vendor parcel for the current cart, without ordering —
    same computation as checkout_cart, so the amount shown never differs."""
    rows = await _load_checkout_rows(db, user)
    _, destination = await _resolve_destination(db, data)
    tiers = await delivery_repository.list_all(db)

    vendors: list[DeliveryQuoteVendorRead] = []
    items_total = 0
    for vendor_items in _group_by_vendor(rows).values():
        vendor = vendor_items[0][3]
        origin = (vendor.latitude, vendor.longitude)
        fee = compute_fee(tiers, origin, destination)
        estimate = estimate_delivery_window(
            transit_days=compute_transit_days(tiers, origin, destination),
            preparation_days=vendor.preparation_days,
            from_date=date.today(),
        )
        vendors.append(
            DeliveryQuoteVendorRead(
                vendor_id=vendor.id,
                shop_name=vendor.shop_name,
                delivery_fee=fee,
                estimated_delivery_min=estimate.min_date,
                estimated_delivery_max=estimate.max_date,
            )
        )
        items_total += _vendor_amount(vendor_items)
    delivery_total = sum(v.delivery_fee for v in vendors)
    return DeliveryQuoteRead(
        vendors=vendors, items_total=items_total, delivery_total=delivery_total, total=items_total + delivery_total
    )


async def checkout_cart(db: AsyncSession, user: User, data: CheckoutRequest) -> Order:
    rows = await _load_checkout_rows(db, user)

    for cart_item, product, variant, _vendor in rows:
        if product.status != ProductStatus.ACTIVE:
            raise ConflictError(f"Le produit « {product.name} » n'est plus disponible.")
        available = variant.stock if variant is not None else product.stock
        if available < cart_item.quantity:
            label = f" ({variant.label()})" if variant is not None else ""
            raise ConflictError(f"Stock insuffisant pour « {product.name}{label} » (disponible : {available}).")

    by_vendor = _group_by_vendor(rows)
    pickup_point_id, destination = await _resolve_destination(db, data)
    tiers = await delivery_repository.list_all(db)
    delivery_fees = {
        vendor_id: compute_fee(tiers, (items[0][3].latitude, items[0][3].longitude), destination)
        for vendor_id, items in by_vendor.items()
    }
    grand_total = sum(_vendor_amount(items) for items in by_vendor.values()) + sum(delivery_fees.values())
    if data.payment_method == PaymentMethod.WALLET:
        # Refus avant toute écriture ; le débit lui-même (compte verrouillé)
        # revérifie le solde, voir buyer_service.pay_order.
        await buyer_service.ensure_can_pay(db, user, grand_total)

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
        delivery_latitude=destination[0],
        delivery_longitude=destination[1],
    )
    redirect_url = await payments_service.create_payment_for_order(
        db, order, payer_phone=data.payer_phone or user.phone
    )

    # Capturé ici (plutôt que relu après coup) pour notifier chaque vendeur
    # une fois la commande commitée, sans dépendre d'objets déjà chargés
    # avant le commit — voir la boucle de notification plus bas.
    vendor_notifications: list[tuple[uuid.UUID, str, int, int]] = []

    for vendor_items in by_vendor.values():
        vendor = vendor_items[0][3]
        amount = _vendor_amount(vendor_items)
        commission = _commission_amount(amount, Decimal(str(vendor.commission_rate)))
        # Figée au checkout — voir le commentaire sur SubOrder.estimated_delivery_min
        # dans app/orders/models.py pour pourquoi ce n'est pas recalculé à la volée.
        estimate = estimate_delivery_window(
            transit_days=compute_transit_days(tiers, (vendor.latitude, vendor.longitude), destination),
            preparation_days=vendor.preparation_days,
            from_date=date.today(),
        )

        sub_order = await repository.create_sub_order(
            db,
            order_id=order.id,
            vendor_id=vendor.id,
            amount=amount,
            commission=commission,
            delivery_fee=delivery_fees[vendor.id],
            shop_name=vendor.shop_name,
            estimated_delivery_min=estimate.min_date,
            estimated_delivery_max=estimate.max_date,
        )

        for cart_item, product, variant, _ in vendor_items:
            await repository.create_order_item(
                db,
                sub_order_id=sub_order.id,
                product_id=product.id,
                product_name=product.name,
                quantity=cart_item.quantity,
                unit_price=_line_unit_price(product, variant),
                variant_id=variant.id if variant is not None else None,
                variant_label=variant.label() if variant is not None else None,
            )
            if variant is not None:
                variant.stock -= cart_item.quantity
            product.stock -= cart_item.quantity

        vendor_notifications.append((vendor.user_id, vendor.shop_name, len(vendor_items), amount))

    await cart_repository.clear_for_user(db, user.id)
    await db.commit()

    for vendor_user_id, shop_name, item_count, amount in vendor_notifications:
        await notifications_service.notify_order_received(
            db, vendor_user_id=vendor_user_id, shop_name=shop_name, order_id=order.id, item_count=item_count, amount=amount
        )

    final_order = await get_order(db, user, order.id)
    # Transitoire : jamais une colonne, voir OrderRead.payment_redirect_url.
    final_order.payment_redirect_url = redirect_url
    return final_order


async def get_order(db: AsyncSession, user: User, order_id: uuid.UUID) -> Order:
    order = await repository.get_order_by_id(db, order_id)
    if order is None or (order.user_id != user.id and user.role != UserRole.ADMIN):
        raise NotFoundError("Commande introuvable.")
    payment = await payments_repository.get_by_order_id(db, order.id)
    _attach_payment_status(order, payment.status if payment else None)
    # Affiché tant que le remboursement n'est pas confirmé — voir
    # cancel_order et payments_service.initiate_refund.
    order.refund_delay_hours = None
    if payment is not None and payment.status == PaymentStatus.REFUND_PENDING:
        refund_settings = await payments_service.get_refund_settings(db)
        order.refund_delay_hours = refund_settings.refund_delay_hours
    order.wallet_refunded_amount = (await buyer_service.refunded_amounts(db, [order.id])).get(order.id, 0)
    await _attach_pickup_point_contacts(db, order, order.pickup_point_id)
    for sub_order in order.sub_orders:
        await _attach_product_images(db, sub_order)
        await _attach_courier_info(db, sub_order)
    return _attach_handoff_flags(order)


async def sync_payment(db: AsyncSession, user: User, order_id: uuid.UUID) -> Order:
    """Reconciles an online payment still PENDING against Djomy — called by
    the buyer's browser right after returning from the Djomy portal, as a
    fallback for a webhook that hasn't arrived yet (or, in dev, never will —
    Djomy can't reach a local machine). No-op otherwise (see
    payments_service.sync_pending_payment)."""
    order = await repository.get_order_by_id(db, order_id)
    if order is None or (order.user_id != user.id and user.role != UserRole.ADMIN):
        raise NotFoundError("Commande introuvable.")
    await payments_service.sync_pending_payment(db, order)
    return await get_order(db, user, order_id)


async def list_my_orders(db: AsyncSession, user: User) -> list[Order]:
    orders = await repository.list_orders_for_user(db, user.id)
    status_map = await payments_repository.get_status_map(db, [order.id for order in orders])
    refunded = await buyer_service.refunded_amounts(db, [order.id for order in orders])
    for order in orders:
        _attach_payment_status(order, status_map.get(order.id))
        order.wallet_refunded_amount = refunded.get(order.id, 0)
        await _attach_pickup_point_contacts(db, order, order.pickup_point_id)
        for sub_order in order.sub_orders:
            await _attach_product_images(db, sub_order)
            await _attach_courier_info(db, sub_order)
    return [_attach_handoff_flags(order) for order in orders]


async def cancel_order(
    db: AsyncSession, user: User, order_id: uuid.UUID, data: OrderCancelRequest | None = None
) -> Order:
    data = data or OrderCancelRequest()
    order = await get_order(db, user, order_id)

    if any(sub_order.status != OrderStatus.PENDING for sub_order in order.sub_orders):
        raise ConflictError(
            "Cette commande ne peut plus être annulée : un vendeur a déjà commencé à la traiter."
        )

    # Un paiement en ligne déjà capturé n'est pas rendu par la seule
    # annulation de la commande — on déclenche un remboursement (payout
    # Djomy vers le compte du payeur, voir payments_service.initiate_refund)
    # avant de toucher quoi que ce soit d'autre : si Djomy refuse (solde
    # marchand insuffisant, etc.), toute la commande doit rester intacte
    # plutôt que d'annuler sans que l'argent ne revienne.
    payment = await payments_repository.get_by_order_id(db, order.id)
    refund_initiated = False
    is_paid = payment is not None and payment.status == PaymentStatus.PAID
    to_wallet = is_paid and (
        payment.method == PaymentMethod.WALLET
        or (payment.method == PaymentMethod.ONLINE and data.refund_to == "wallet" and await buyer_service.is_enabled(db))
    )
    if to_wallet:
        # Remboursement immédiat sur le solde NdjouriBank (séquestre → solde).
        await buyer_service.refund_to_wallet(db, order, order.total, reason="annulée par l'acheteur")
        payment.status = PaymentStatus.REFUNDED
        refund_initiated = True
    elif is_paid and payment.method == PaymentMethod.ONLINE:
        buyer = await user_repository.get_by_id(db, order.user_id)
        beneficiary_name = " ".join(filter(None, [buyer.first_name, buyer.last_name])).strip() or "Client netmarket"
        await payments_service.initiate_refund(
            db, payment, order_reference=str(order.id), beneficiary_name=beneficiary_name
        )
        refund_initiated = True

    for sub_order in order.sub_orders:
        sub_order.status = OrderStatus.CANCELLED
        for item in sub_order.items:
            product = await catalog_repository.get_product_by_id(db, item.product_id)
            if product is not None:
                product.stock += item.quantity
            # item.variant_id peut déjà être None si la variante a été
            # supprimée depuis (ON DELETE SET NULL) — dans ce cas seul le
            # stock produit ci-dessus est restauré, comportement attendu.
            if item.variant_id is not None:
                variant = await catalog_repository.get_variant_by_id(db, item.variant_id)
                if variant is not None:
                    variant.stock += item.quantity

    order.status = OrderStatus.CANCELLED
    if not refund_initiated:
        await payments_service.mark_cancelled(db, order.id)
    await db.commit()
    for sub_order in order.sub_orders:
        await _signal_parcel_followers(db, sub_order)
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
    # Ces trois derniers ne servent qu'à SubOrderRead (acheteur, voir
    # app/orders/schemas.py) — VendorSubOrderRead/AdminSubOrderRead les
    # ignorent simplement (attributs transitoires surnuméraires, sans risque).
    sub_order.courier_status = None
    sub_order.courier_average_rating = None
    sub_order.courier_review_count = 0
    if sub_order.courier_id is not None:
        courier = await courier_repository.get_by_id(db, sub_order.courier_id)
        if courier is not None:
            sub_order.courier_name = courier.full_name
            sub_order.courier_phone = courier.phone
            sub_order.courier_status = courier.status.value
            average, count = await courier_repository.get_rating_summary(db, courier.id)
            sub_order.courier_average_rating = average
            sub_order.courier_review_count = count
    return sub_order


async def _attach_dispatch_offer_info(db: AsyncSession, sub_order: SubOrder) -> SubOrder:
    sub_order.dispatch_offered_courier_name = None
    if sub_order.dispatch_offered_courier_id is not None:
        courier = await courier_repository.get_by_id(db, sub_order.dispatch_offered_courier_id)
        if courier is not None:
            sub_order.dispatch_offered_courier_name = courier.full_name or courier.phone
    return sub_order


async def _attach_product_images(db: AsyncSession, sub_order: SubOrder) -> SubOrder:
    # Même logique que app/cart/service.py::get_cart pour product_image :
    # variante d'abord si elle a ses propres photos, sinon celles du produit.
    for item in sub_order.items:
        item.product_image = None
        product = await catalog_repository.get_product_by_id(db, item.product_id)
        if product is None:
            continue
        variant = await catalog_repository.get_variant_by_id(db, item.variant_id) if item.variant_id else None
        images = (variant.images if (variant is not None and variant.images) else None) or product.images
        item.product_image = images[0] if images else None
    return sub_order


async def _attach_pickup_point_contacts(db: AsyncSession, target, pickup_point_id: uuid.UUID | None) -> None:
    # Live lookup, deliberately not frozen: a pickup point can have several
    # managers, and who's currently staffing it can change after the order
    # was placed — unlike delivery_address/recipient_*, there's no single
    # "the" contact to snapshot at checkout time.
    # pickup_point_name/rating ne servent qu'à OrderRead (acheteur, voir
    # app/orders/schemas.py) — les schémas vendeur/livreur/gestionnaire les
    # ignorent simplement (attributs transitoires surnuméraires, sans risque).
    target.pickup_point_name = None
    target.pickup_point_average_rating = None
    target.pickup_point_review_count = 0
    if pickup_point_id is None:
        target.pickup_point_contacts = []
        return
    managers = await pickup_point_manager_repository.list_by_pickup_point(db, pickup_point_id)
    target.pickup_point_contacts = [{"name": m.full_name, "phone": m.phone} for m in managers]
    point = await pickup_points_repository.get_by_id(db, pickup_point_id)
    if point is not None:
        target.pickup_point_name = point.name
        average, count = await pickup_points_repository.get_rating_summary(db, pickup_point_id)
        target.pickup_point_average_rating = average
        target.pickup_point_review_count = count


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
        await _attach_product_images(db, so)
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

    previous_courier_id = sub_order.courier_id
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
    await _signal_parcel_followers(db, updated, extra_courier_ids={previous_courier_id})
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    await _attach_dispatch_offer_info(db, updated)
    await _attach_product_images(db, updated)
    return await _attach_courier_info(db, updated)


def _attach_dropoff_flag(sub_order: SubOrder) -> SubOrder:
    sub_order.dropoff_handoff_ready = _is_couriers_dropoff_turn(sub_order)
    return sub_order


async def list_my_deliveries(db: AsyncSession, user: User) -> list[SubOrder]:
    courier = await courier_repository.get_by_user_id(db, user.id)
    if courier is None:
        raise NotFoundError("Vous n'avez pas de profil livreur.")
    sub_orders = await repository.list_sub_orders_for_courier(db, courier.id)
    for so in sub_orders:
        _attach_dropoff_flag(_attach_delivery_address(so))
        await _attach_pickup_point_contacts(db, so, so.order.pickup_point_id)
        await _attach_product_images(db, so)
    return sub_orders


async def list_my_point_deliveries(db: AsyncSession, user: User) -> list[SubOrder]:
    manager = await pickup_point_manager_repository.get_by_user_id(db, user.id)
    if manager is None:
        raise NotFoundError("Vous n'avez pas de profil gestionnaire de point de retrait.")
    sub_orders = await repository.list_sub_orders_for_pickup_point(db, manager.pickup_point_id)
    customers: dict[uuid.UUID, User | None] = {}
    result = []
    for so in sub_orders:
        _attach_delivery_address(so)
        await _attach_courier_info(db, so)
        await _attach_product_images(db, so)
        # Le client qui viendra retirer le colis : pour le reconnaître, le
        # retrouver par son nom et l'appeler si le colis attend trop.
        buyer_id = so.order.user_id
        if buyer_id not in customers:
            customers[buyer_id] = await user_repository.get_by_id(db, buyer_id)
        buyer = customers[buyer_id]
        so.customer_name = (
            " ".join(filter(None, [buyer.first_name, buyer.last_name])).strip() or None if buyer else None
        )
        so.customer_phone = buyer.phone if buyer else None
        result.append(so)
    return result


async def update_storage_location(
    db: AsyncSession, user: User, sub_order_id: uuid.UUID, storage_location: str | None
) -> SubOrder:
    """Le gestionnaire note où il a rangé le colis (étagère, case...) —
    purement informatif, jamais vérifié contre le statut de la sous-commande :
    il peut le renseigner dès la réception ou le corriger à tout moment avant
    la remise, sans que ça n'affecte le cycle de vie de la commande."""
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")
    if sub_order.order.delivery_type != DeliveryType.PICKUP_POINT:
        raise ConflictError("Cette commande n'est pas une livraison en point de retrait.")

    manager = await pickup_point_manager_repository.get_by_user_id(db, user.id)
    if manager is None or manager.pickup_point_id != sub_order.order.pickup_point_id:
        raise ForbiddenError("Cette sous-commande ne fait pas partie de votre point de retrait.")

    sub_order.storage_location = storage_location
    await db.commit()

    updated = await repository.get_sub_order_by_id(db, sub_order_id)
    _attach_delivery_address(updated)
    await _attach_courier_info(db, updated)
    await _attach_product_images(db, updated)
    return updated


# Étapes où le colis change de mains : scan obligatoire.
HANDOFF_STATUSES = {OrderStatus.ARRIVED_AT_PICKUP_POINT, OrderStatus.DELIVERED}


async def update_sub_order_status(
    db: AsyncSession, user: User, sub_order_id: uuid.UUID, data: SubOrderStatusUpdate, *, via_scan: bool = False
) -> SubOrder:
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")

    vendor = await vendor_repository.get_by_id(db, sub_order.vendor_id)
    is_owner_vendor = vendor is not None and vendor.user_id == user.id

    # Rôles évalués indépendamment : un même compte peut être à la fois le
    # vendeur de la sous-commande et le gestionnaire du point de retrait (sa
    # boutique EST le point, voir admin_link_vendor_as_manager) — il doit
    # alors pouvoir confirmer la réception de ses propres colis au point.
    is_assigned_courier = False
    if sub_order.courier_id is not None:
        courier = await courier_repository.get_by_id(db, sub_order.courier_id)
        is_assigned_courier = courier is not None and courier.user_id == user.id

    is_assigned_point_manager = False
    if sub_order.order.pickup_point_id is not None:
        manager = await pickup_point_manager_repository.get_by_user_id(db, user.id)
        is_assigned_point_manager = (
            manager is not None and manager.pickup_point_id == sub_order.order.pickup_point_id
        )

    if not is_owner_vendor and not is_assigned_courier and not is_assigned_point_manager:
        raise ForbiddenError("Cette sous-commande ne fait pas partie de votre boutique.")

    is_pickup = sub_order.order.delivery_type == DeliveryType.PICKUP_POINT
    if data.status in HANDOFF_STATUSES:
        # Remise physique du colis (au client, ou au point de retrait) :
        # uniquement par scan du QR de la personne qui remet le colis —
        # jamais par un bouton (voir confirm_delivery_by_code).
        if not via_scan:
            raise ForbiddenError(
                "La remise d'un colis se confirme uniquement en scannant le QR code présenté "
                "(client, ou livreur au point de retrait)."
            )
        # Le livreur scanne le client pour une livraison à domicile ; pour un
        # point de retrait, c'est le gestionnaire qui scanne (livreur au
        # dépôt, puis client au retrait).
        allowed = is_assigned_point_manager if is_pickup else (
            is_assigned_courier and data.status == OrderStatus.DELIVERED
        )
        if not allowed:
            raise ForbiddenError(
                "Un livreur confirme la remise au client pour une livraison à domicile ; pour un point de "
                "retrait, c'est le gestionnaire du point qui confirme la réception et la remise."
            )
    elif not is_owner_vendor:
        # Accepter, préparer, expédier, annuler : toujours le vendeur.
        raise ForbiddenError("Seul le vendeur peut faire avancer cette commande avant son expédition.")

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
            if item.variant_id is not None:
                variant = await catalog_repository.get_variant_by_id(db, item.variant_id)
                if variant is not None:
                    variant.stock += item.quantity

    sub_order.status = data.status
    handoff.reset(sub_order)
    await db.flush()

    order = await repository.get_order_by_id(db, sub_order.order_id)
    order.status = _compute_order_status(order.sub_orders)
    if data.status == OrderStatus.CANCELLED and order.payment_method == PaymentMethod.WALLET:
        # Payé avec le solde NdjouriBank : la part de cette boutique revient
        # tout de suite sur le solde de l'acheteur.
        payment = await payments_repository.get_by_order_id(db, order.id)
        if payment is not None and payment.status == PaymentStatus.PAID:
            await buyer_service.refund_to_wallet(
                db,
                order,
                sub_order.amount + sub_order.delivery_fee,
                reason=f"{sub_order.shop_name} a annulé",
                sub_order_id=sub_order.id,
            )
            if order.status == OrderStatus.CANCELLED:
                payment.status = PaymentStatus.REFUNDED
    if data.status == OrderStatus.DELIVERED:
        # Paiement en ligne : répartition du séquestre entre vendeur, livreur,
        # point de retrait et Ndjouri (voir app/wallets/service.py).
        await wallets_service.settle_sub_order(db, order, sub_order)
    if order.status == OrderStatus.DELIVERED and order.payment_method == PaymentMethod.CASH_ON_DELIVERY:
        # Cash on delivery: money only actually changes hands once every
        # vendor in the order has delivered — see payments/provider.py. For
        # an online payment, the Djomy webhook is the only source of truth
        # on whether it actually succeeded — delivery must never overwrite a
        # FAILED/CANCELLED payment to PAID just because the parcel arrived.
        await payments_service.mark_paid(db, order.id)

    await db.commit()

    buyer = await user_repository.get_by_id(db, order.user_id)
    if buyer is not None:
        await notifications_service.notify_sub_order_status_changed(db, buyer, sub_order)

    updated = await repository.get_sub_order_by_id(db, sub_order_id)
    await _signal_parcel_followers(db, updated)
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    await _attach_product_images(db, updated)
    return await _attach_courier_info(db, updated)


async def _handoff_candidates(db: AsyncSession, user: User) -> list[SubOrder]:
    """Colis dont l'utilisateur peut scanner le QR à l'étape actuelle : ses
    livraisons à domicile expédiées (livreur), et les colis de son point en
    attente de dépôt ou de retrait (gestionnaire)."""
    candidates: list[SubOrder] = []
    courier = await courier_repository.get_by_user_id(db, user.id)
    if courier is not None:
        for so in await repository.list_sub_orders_for_courier(db, courier.id):
            if so.status == OrderStatus.SHIPPED and so.order.delivery_type == DeliveryType.HOME_DELIVERY:
                candidates.append(so)
    manager = await pickup_point_manager_repository.get_by_user_id(db, user.id)
    if manager is not None:
        for so in await repository.list_sub_orders_for_pickup_point(db, manager.pickup_point_id):
            if so.status in (OrderStatus.SHIPPED, OrderStatus.ARRIVED_AT_PICKUP_POINT):
                candidates.append(so)
    return candidates


async def confirm_delivery_by_code(db: AsyncSession, user: User, raw_code: str) -> SubOrder:
    """Le livreur ou le gestionnaire affecté scanne un QR de remise (celui du
    client, ou — dépôt au point de retrait — celui du livreur). Le code est
    comparé uniquement aux colis de cette personne (voir app/orders/handoff.py) ;
    l'étape suivante passe ensuite par le même chemin que toute transition
    (contrôle des rôles compris), en mode scan.

    home_delivery : shipped → delivered (QR client, scanné par le livreur).
    pickup_point : shipped → arrived_at_pickup_point (QR livreur, scanné par
    le gestionnaire), puis arrived_at_pickup_point → delivered (QR client,
    scanné par le gestionnaire)."""
    code = handoff.normalize(raw_code)
    match = next((so for so in await _handoff_candidates(db, user) if handoff.matches(so, code)), None)
    if match is None:
        raise ConflictError("QR code invalide, expiré ou ne concernant aucun de vos colis.")

    next_statuses = _allowed_next_statuses(match.status, match.order.delivery_type)
    next_status = next(iter(next_statuses & HANDOFF_STATUSES), None)
    if next_status is None:
        raise ConflictError("QR code invalide, expiré ou ne concernant aucun de vos colis.")
    return await update_sub_order_status(
        db, user, match.id, SubOrderStatusUpdate(status=next_status), via_scan=True
    )


async def get_handoff_code(db: AsyncSession, user: User, sub_order_id: uuid.UUID) -> tuple[str, int]:
    """QR de remise à afficher : celui de l'acheteur (c'est son tour), ou celui
    du livreur affecté pour un dépôt au point de retrait."""
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None:
        raise NotFoundError("Sous-commande introuvable.")
    order = sub_order.order
    is_buyer = order.user_id == user.id and _is_buyers_turn(sub_order, order.delivery_type)
    is_dropping_courier = False
    if not is_buyer and sub_order.courier_id is not None and _is_couriers_dropoff_turn(sub_order):
        courier = await courier_repository.get_by_id(db, sub_order.courier_id)
        is_dropping_courier = courier is not None and courier.user_id == user.id
    if not is_buyer and not is_dropping_courier:
        raise NotFoundError("Aucun QR code à présenter pour ce colis.")
    handoff.ensure_stage_nonce(sub_order)
    await db.commit()
    return handoff.current_code(sub_order)


async def _courier_earning(db: AsyncSession, sub_order: SubOrder) -> int:
    """Part des frais de livraison qui revient au livreur (réglage admin, voir
    app/wallets/service.py::settle_sub_order)."""
    settings_row = await payments_repository.get_settings(db)
    return round((sub_order.delivery_fee or 0) * settings_row.courier_delivery_share_percent / 100)


async def get_delivery_offer(db: AsyncSession, user: User, sub_order_id: uuid.UUID) -> dict:
    """Détail d'une demande de livraison pour le livreur à qui elle est
    proposée : son gain, les distances, où récupérer et où livrer — jamais le
    prix des articles."""
    courier = await courier_repository.get_by_user_id(db, user.id)
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if courier is None or sub_order is None or sub_order.dispatch_offered_courier_id != courier.id:
        raise NotFoundError("Cette demande de livraison n'est plus disponible.")
    order = sub_order.order
    vendor = await vendor_repository.get_by_id(db, sub_order.vendor_id)

    def distance(a_lat, a_lng, b_lat, b_lng) -> float | None:
        if None in (a_lat, a_lng, b_lat, b_lng):
            return None
        return round(haversine_km(a_lat, a_lng, b_lat, b_lng), 1)

    offer = {
        "sub_order_id": sub_order.id,
        "shop_name": sub_order.shop_name,
        "shop_zone": vendor.zone if vendor else None,
        "distance_to_shop_km": distance(
            courier.latitude, courier.longitude, vendor.latitude if vendor else None, vendor.longitude if vendor else None
        ),
        "delivery_distance_km": distance(
            vendor.latitude if vendor else None,
            vendor.longitude if vendor else None,
            order.delivery_latitude,
            order.delivery_longitude,
        ),
        "courier_earning": await _courier_earning(db, sub_order),
        "item_count": sum(item.quantity for item in sub_order.items),
        "delivery_type": order.delivery_type,
        "destination_zone": order.delivery_zone or order.delivery_address,
        "delivery_instructions": order.delivery_instructions,
        "recipient_name": order.recipient_name,
        "pickup_point_name": None,
        "pickup_point_zone": None,
        "pickup_point_contacts": [],
        "expires_in_seconds": OFFER_TIMEOUT_SECONDS,
    }
    if order.delivery_type == DeliveryType.PICKUP_POINT and order.pickup_point_id is not None:
        point = await pickup_points_repository.get_by_id(db, order.pickup_point_id)
        managers = await pickup_point_manager_repository.list_by_pickup_point(db, order.pickup_point_id)
        offer["pickup_point_name"] = point.name if point else None
        offer["pickup_point_zone"] = point.zone if point else None
        offer["pickup_point_contacts"] = [{"name": m.full_name, "phone": m.phone} for m in managers]
    return offer


async def _signal_parcel_followers(
    db: AsyncSession, sub_order: SubOrder, *, extra_courier_ids: set[uuid.UUID | None] | None = None
) -> None:
    """Prévient en direct (signal silencieux) le livreur et les gestionnaires
    du point concernés qu'un colis a changé — leur écran relit sa liste."""
    user_ids: set[uuid.UUID] = set()
    for courier_id in {sub_order.courier_id, *(extra_courier_ids or set())}:
        if courier_id is not None:
            courier = await courier_repository.get_by_id(db, courier_id)
            if courier is not None:
                user_ids.add(courier.user_id)
    if sub_order.order.pickup_point_id is not None:
        for manager in await pickup_point_manager_repository.list_by_pickup_point(db, sub_order.order.pickup_point_id):
            user_ids.add(manager.user_id)
    await notifications_service.push_refresh(user_ids, "deliveries")


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
        courier_earning=await _courier_earning(db, sub_order),
        distance_km=haversine_km(vendor.latitude, vendor.longitude, first.latitude, first.longitude),
    )

    _dispatch_events[sub_order.id] = asyncio.Event()
    asyncio.create_task(_run_dispatch(sub_order.id, vendor.latitude, vendor.longitude))

    updated = await repository.get_sub_order_by_id(db, sub_order_id)
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    await _attach_dispatch_offer_info(db, updated)
    await _attach_product_images(db, updated)
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
            courier_earning=await _courier_earning(db, sub_order),
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
    await _signal_parcel_followers(db, updated)
    _attach_delivery_address(updated)
    await _attach_pickup_point_contacts(db, updated, updated.order.pickup_point_id)
    await _attach_product_images(db, updated)
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
