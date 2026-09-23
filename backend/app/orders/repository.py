"""Database access for orders, sub-orders and order items."""

import uuid
from datetime import date, timedelta

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import DATE as PG_DATE
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.orders.models import DeliveryType, Order, OrderItem, OrderStatus, PaymentMethod, SubOrder


async def has_delivered_product_for_user(db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID) -> bool:
    """True once a delivered sub-order of this user included this product —
    the "avis après livraison" gate for app/reviews/service.py::create_review."""
    stmt = (
        select(OrderItem.id)
        .join(SubOrder, OrderItem.sub_order_id == SubOrder.id)
        .join(Order, SubOrder.order_id == Order.id)
        .where(Order.user_id == user_id, OrderItem.product_id == product_id, SubOrder.status == OrderStatus.DELIVERED)
        .limit(1)
    )
    return (await db.execute(stmt)).first() is not None


async def has_delivered_by_courier_for_user(db: AsyncSession, user_id: uuid.UUID, courier_id: uuid.UUID) -> bool:
    """True once this courier actually delivered a sub-order of this user —
    the "avis après livraison" gate for app/couriers/service.py::create_review."""
    stmt = (
        select(SubOrder.id)
        .join(Order, SubOrder.order_id == Order.id)
        .where(Order.user_id == user_id, SubOrder.courier_id == courier_id, SubOrder.status == OrderStatus.DELIVERED)
        .limit(1)
    )
    return (await db.execute(stmt)).first() is not None


async def has_used_pickup_point_for_user(db: AsyncSession, user_id: uuid.UUID, pickup_point_id: uuid.UUID) -> bool:
    """True once this user actually received a delivered order routed through
    this pickup point — the "avis après retrait" gate for
    app/pickup_points/service.py::create_review. pickup_point_id lives on
    Order (one point per order, unlike courier_id which is per sub-order),
    so any delivered sub-order of that order is enough."""
    stmt = (
        select(Order.id)
        .join(SubOrder, SubOrder.order_id == Order.id)
        .where(
            Order.user_id == user_id,
            Order.pickup_point_id == pickup_point_id,
            SubOrder.status == OrderStatus.DELIVERED,
        )
        .limit(1)
    )
    return (await db.execute(stmt)).first() is not None


async def create_order(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    delivery_address: str,
    delivery_type: DeliveryType,
    payment_method: PaymentMethod,
    total: int,
    pickup_point_id: uuid.UUID | None = None,
    delivery_zone: str | None = None,
    delivery_instructions: str | None = None,
    recipient_name: str | None = None,
    recipient_phone: str | None = None,
) -> Order:
    order = Order(
        user_id=user_id,
        delivery_address=delivery_address,
        delivery_type=delivery_type,
        payment_method=payment_method,
        total=total,
        pickup_point_id=pickup_point_id,
        delivery_zone=delivery_zone,
        delivery_instructions=delivery_instructions,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
    )
    db.add(order)
    await db.flush()
    return order


async def create_sub_order(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    vendor_id: uuid.UUID,
    amount: int,
    commission: int,
    delivery_fee: int = 0,
    shop_name: str,
    estimated_delivery_min: date | None = None,
    estimated_delivery_max: date | None = None,
) -> SubOrder:
    sub_order = SubOrder(
        order_id=order_id,
        vendor_id=vendor_id,
        amount=amount,
        commission=commission,
        delivery_fee=delivery_fee,
        shop_name=shop_name,
        estimated_delivery_min=estimated_delivery_min,
        estimated_delivery_max=estimated_delivery_max,
    )
    db.add(sub_order)
    await db.flush()
    return sub_order


async def create_order_item(
    db: AsyncSession,
    *,
    sub_order_id: uuid.UUID,
    product_id: uuid.UUID,
    product_name: str,
    quantity: int,
    unit_price: int,
    variant_id: uuid.UUID | None = None,
    variant_label: str | None = None,
) -> OrderItem:
    item = OrderItem(
        sub_order_id=sub_order_id,
        product_id=product_id,
        product_name=product_name,
        quantity=quantity,
        unit_price=unit_price,
        variant_id=variant_id,
        variant_label=variant_label,
    )
    db.add(item)
    await db.flush()
    return item


async def get_order_by_id(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    stmt = (
        select(Order)
        .options(selectinload(Order.sub_orders).selectinload(SubOrder.items))
        .where(Order.id == order_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_orders_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Order]:
    stmt = (
        select(Order)
        .options(selectinload(Order.sub_orders).selectinload(SubOrder.items))
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_sub_order_by_id(db: AsyncSession, sub_order_id: uuid.UUID) -> SubOrder | None:
    stmt = (
        select(SubOrder)
        .options(selectinload(SubOrder.items), selectinload(SubOrder.order))
        .where(SubOrder.id == sub_order_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_sub_orders_for_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> list[SubOrder]:
    stmt = (
        select(SubOrder)
        .options(selectinload(SubOrder.items), selectinload(SubOrder.order))
        .where(SubOrder.vendor_id == vendor_id)
        .order_by(SubOrder.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_sub_orders_for_courier(db: AsyncSession, courier_id: uuid.UUID) -> list[SubOrder]:
    stmt = (
        select(SubOrder)
        .options(selectinload(SubOrder.items), selectinload(SubOrder.order))
        .where(SubOrder.courier_id == courier_id)
        .order_by(SubOrder.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_sub_orders_for_pickup_point(db: AsyncSession, pickup_point_id: uuid.UUID) -> list[SubOrder]:
    # Contrairement à list_sub_orders_for_courier, le point n'est pas porté
    # par SubOrder mais par l'Order parent (un seul point par commande,
    # partagé par toutes ses sous-commandes) — d'où la jointure.
    stmt = (
        select(SubOrder)
        .join(Order, SubOrder.order_id == Order.id)
        .options(selectinload(SubOrder.items), selectinload(SubOrder.order))
        .where(Order.pickup_point_id == pickup_point_id)
        .order_by(SubOrder.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_vendor_dashboard_counts(db: AsyncSession, vendor_id: uuid.UUID) -> dict:
    """Sub-order counts per status, plus revenue/commission for delivered ones.

    "Revenue" only counts delivered sub-orders: with cash-on-delivery, money
    only actually changes hands once the order is delivered.
    """
    status_stmt = select(SubOrder.status, func.count()).where(SubOrder.vendor_id == vendor_id).group_by(SubOrder.status)
    status_counts = {status.value: 0 for status in OrderStatus}
    for status, count in (await db.execute(status_stmt)).all():
        status_counts[status.value] = count

    revenue_stmt = select(
        func.coalesce(func.sum(SubOrder.amount), 0), func.coalesce(func.sum(SubOrder.commission), 0)
    ).where(SubOrder.vendor_id == vendor_id, SubOrder.status == OrderStatus.DELIVERED)
    revenue_delivered, commission_due = (await db.execute(revenue_stmt)).one()

    return {
        "status_counts": status_counts,
        "revenue_delivered": int(revenue_delivered),
        "commission_due": int(commission_due),
    }


async def get_daily_order_counts(db: AsyncSession, vendor_id: uuid.UUID, days: int) -> dict[date, int]:
    """Sub-orders received per day, last `days` days (Guinea has no DST/UTC offset,
    so grouping the timestamptz column by date needs no timezone conversion).

    Only the days with at least one order come back — the caller zero-fills the
    rest, since a bar/line chart needs every day on the axis, not just the ones
    with data.
    """
    since = date.today() - timedelta(days=days - 1)
    day_col = cast(SubOrder.created_at, PG_DATE)
    stmt = (
        select(day_col.label("day"), func.count().label("count"))
        .where(SubOrder.vendor_id == vendor_id, day_col >= since)
        .group_by(day_col)
    )
    rows = (await db.execute(stmt)).all()
    return {row.day: row.count for row in rows}
