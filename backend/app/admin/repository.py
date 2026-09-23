"""Aggregate read queries for the admin dashboard: counts, sales, top rankings."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Product
from app.core.pagination import PageParams
from app.orders.models import Order, OrderItem, OrderStatus, SubOrder
from app.pickup_points.models import PickupPoint
from app.users.models import User
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


async def get_vendor_owner(db: AsyncSession, vendor_id: uuid.UUID) -> User | None:
    """The account behind a boutique — Vendor has no relationship to User,
    joined here rather than in app/vendors/repository.py since this is
    admin-only reporting, not something the vendor/catalog modules need."""
    stmt = select(User).join(Vendor, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    return (await db.execute(stmt)).scalar_one_or_none()


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
