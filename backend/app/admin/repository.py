"""Aggregate read queries for the admin dashboard: counts, sales, top rankings."""

import uuid
from datetime import date, datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Product
from app.core.pagination import PageParams
from app.orders.models import Order, OrderItem, OrderStatus, PaymentMethod, SubOrder
from app.pickup_points.models import PickupPoint
from app.users.models import User, UserRole
from app.vendors.models import Vendor, VendorStatus


async def count_vendors_by_status(db: AsyncSession) -> dict[str, int]:
    stmt = select(Vendor.status, func.count()).group_by(Vendor.status)
    counts = {status.value: 0 for status in VendorStatus}
    for status, count in (await db.execute(stmt)).all():
        counts[status.value] = count
    return counts


async def count_products(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Product))).scalar_one()


async def count_orders_by_status(db: AsyncSession) -> dict[str, int]:
    stmt = select(Order.status, func.count()).group_by(Order.status)
    counts = {status.value: 0 for status in OrderStatus}
    for status, count in (await db.execute(stmt)).all():
        counts[status.value] = count
    return counts


async def daily_orders(db: AsyncSession, since: datetime) -> dict[date, tuple[int, int]]:
    """Par jour : (commandes passées, montant commandé hors annulées)."""
    day = func.date(Order.created_at)
    stmt = (
        select(
            day,
            func.count(),
            func.coalesce(func.sum(case((Order.status != OrderStatus.CANCELLED, Order.total), else_=0)), 0),
        )
        .where(Order.created_at >= since)
        .group_by(day)
    )
    return {d: (int(count), int(amount)) for d, count, amount in (await db.execute(stmt)).all()}


async def daily_signups(db: AsyncSession, since: datetime) -> dict[date, int]:
    day = func.date(User.created_at)
    stmt = select(day, func.count()).where(User.created_at >= since).group_by(day)
    return {d: int(count) for d, count in (await db.execute(stmt)).all()}


async def count_orders_by_payment_method(db: AsyncSession) -> dict[str, int]:
    stmt = select(Order.payment_method, func.count()).group_by(Order.payment_method)
    counts = {method.value: 0 for method in PaymentMethod}
    for method, count in (await db.execute(stmt)).all():
        counts[method.value] = count
    return counts


async def count_users_by_role(db: AsyncSession) -> dict[str, int]:
    stmt = select(User.role, func.count()).group_by(User.role)
    counts = {role.value: 0 for role in UserRole}
    for role, count in (await db.execute(stmt)).all():
        counts[role.value] = count
    return counts


async def sum_sales_and_commission(db: AsyncSession) -> tuple[int, int]:
    stmt = select(
        func.coalesce(func.sum(SubOrder.amount), 0), func.coalesce(func.sum(SubOrder.commission), 0)
    ).where(SubOrder.status == OrderStatus.DELIVERED)
    total_sales, total_commission = (await db.execute(stmt)).one()
    return int(total_sales), int(total_commission)


async def top_products(db: AsyncSession, limit: int = 5) -> list[tuple]:
    stmt = (
        select(OrderItem.product_id, OrderItem.product_name, func.sum(OrderItem.quantity))
        .join(SubOrder, OrderItem.sub_order_id == SubOrder.id)
        .where(SubOrder.status == OrderStatus.DELIVERED)
        .group_by(OrderItem.product_id, OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).all())


async def top_vendors(db: AsyncSession, limit: int = 5) -> list[tuple]:
    stmt = (
        select(SubOrder.vendor_id, SubOrder.shop_name, func.sum(SubOrder.amount))
        .where(SubOrder.status == OrderStatus.DELIVERED)
        .group_by(SubOrder.vendor_id, SubOrder.shop_name)
        .order_by(func.sum(SubOrder.amount).desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).all())


async def get_vendor_with_owner(db: AsyncSession, vendor_id: uuid.UUID) -> tuple[Vendor, User] | None:
    """A boutique + the account behind it — Vendor has no relationship to
    User, joined here rather than in app/vendors/repository.py since this is
    admin-only reporting, not something the vendor/catalog modules need."""
    stmt = select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    row = (await db.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def count_orders_for_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Order).where(Order.user_id == user_id)
    return (await db.execute(stmt)).scalar_one()


async def get_pickup_point_with_shop(db: AsyncSession, pickup_point_id: uuid.UUID) -> tuple[PickupPoint, str | None] | None:
    stmt = (
        select(PickupPoint, Vendor.shop_name)
        .outerjoin(Vendor, PickupPoint.vendor_id == Vendor.id)
        .where(PickupPoint.id == pickup_point_id)
    )
    row = (await db.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def list_all_orders(
    db: AsyncSession, params: PageParams, status_filter: OrderStatus | None
) -> tuple[list[Order], int]:
    base_stmt = select(Order)
    if status_filter is not None:
        base_stmt = base_stmt.where(Order.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(base_stmt.subquery()))).scalar_one()

    stmt = (
        base_stmt.options(selectinload(Order.sub_orders).selectinload(SubOrder.items))
        .order_by(Order.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


# Colis pas encore arrivés à destination : acceptés par la boutique, en
# préparation ou en route. PENDING (pas encore confirmé) n'a ni livreur ni
# dispatch ; ARRIVED_AT_PICKUP_POINT n'attend plus que l'acheteur.
ACTIVE_DELIVERY_STATUSES = (OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.SHIPPED)


async def list_active_deliveries(db: AsyncSession) -> list[tuple]:
    """(SubOrder, Order, vendor lat, vendor lng, pickup point name) pour la
    carte admin des livraisons en cours. La position de la boutique est lue
    en direct (pas figée au checkout) : c'est là que le livreur va chercher
    le colis aujourd'hui."""
    stmt = (
        select(SubOrder, Order, Vendor.latitude, Vendor.longitude, PickupPoint.name)
        .join(Order, SubOrder.order_id == Order.id)
        .join(Vendor, SubOrder.vendor_id == Vendor.id)
        .outerjoin(PickupPoint, Order.pickup_point_id == PickupPoint.id)
        .where(SubOrder.status.in_(ACTIVE_DELIVERY_STATUSES))
        .order_by(SubOrder.created_at.desc())
    )
    return list((await db.execute(stmt)).all())


# Suivi des livraisons : tout ce qui est entre les mains de la chaîne
# logistique (confirmé → au point de retrait), plus ce qui a été livré depuis
# `since`, pour le compteur du jour. Les annulations ne sont pas remontées :
# la plupart surviennent avant toute prise en charge (commande en attente),
# ce ne sont pas des livraisons.
MONITORED_STATUSES = (*ACTIVE_DELIVERY_STATUSES, OrderStatus.ARRIVED_AT_PICKUP_POINT)


async def list_monitored_deliveries(db: AsyncSession, since: datetime) -> list[tuple]:
    """(SubOrder, Order, buyer User | None, vendor zone, pickup point name)."""
    stmt = (
        select(SubOrder, Order, User, Vendor.zone, PickupPoint.name)
        .join(Order, SubOrder.order_id == Order.id)
        .join(Vendor, SubOrder.vendor_id == Vendor.id)
        .outerjoin(User, Order.user_id == User.id)
        .outerjoin(PickupPoint, Order.pickup_point_id == PickupPoint.id)
        .where(
            or_(
                SubOrder.status.in_(MONITORED_STATUSES),
                and_(SubOrder.status == OrderStatus.DELIVERED, SubOrder.updated_at >= since),
            )
        )
        .order_by(SubOrder.updated_at.desc())
    )
    return list((await db.execute(stmt)).all())
