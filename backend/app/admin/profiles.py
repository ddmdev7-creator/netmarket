"""Fiches détaillées de l'administration : utilisateur, livreur, point de
retrait, et vue d'ensemble des gestionnaires de point."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address
from app.admin.schemas import (
    AdminCourierProfile,
    AdminManagerOverview,
    AdminPickupPointProfile,
    AdminUserProfile,
    AdminUserUpdate,
    DeliveryStats,
    ManagerSummary,
    PickupStats,
    ProfileAddress,
    ProfileCourierLink,
    ProfileDelivery,
    ProfileManagedPoint,
    ProfileOrder,
    ProfileVendorLink,
    ProfileWallet,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.couriers import service as couriers_service
from app.couriers.models import Courier
from app.orders.models import Order, OrderItem, OrderStatus, SubOrder
from app.pickup_point_managers.models import PickupPointManager
from app.pickup_points import service as pickup_points_service
from app.pickup_points.models import PickupPoint
from app.users.models import User
from app.vendors.models import Vendor
from app.wallets import service as wallets_service
from app.wallets.models import AccountKind

RECENT = 10


def _wallet(balance) -> ProfileWallet | None:
    return ProfileWallet(available=balance.available, pending=balance.pending, total=balance.total) if balance else None


def _delivery(sub_order: SubOrder, order: Order) -> ProfileDelivery:
    return ProfileDelivery(
        sub_order_id=sub_order.id,
        order_id=order.id,
        shop_name=sub_order.shop_name,
        status=sub_order.status,
        delivery_type=order.delivery_type,
        delivery_fee=sub_order.delivery_fee,
        updated_at=sub_order.updated_at,
    )


# --- Utilisateur --------------------------------------------------------------------


async def user_profile(db: AsyncSession, user_id: uuid.UUID) -> AdminUserProfile:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Utilisateur introuvable.")

    count, total, last = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(Order.total), 0), func.max(Order.created_at)).where(
                Order.user_id == user.id, Order.status != OrderStatus.CANCELLED
            )
        )
    ).one()
    item_counts = (
        select(SubOrder.order_id, func.sum(OrderItem.quantity).label("n"))
        .join(OrderItem, OrderItem.sub_order_id == SubOrder.id)
        .group_by(SubOrder.order_id)
        .subquery()
    )
    recent = (
        await db.execute(
            select(Order, item_counts.c.n)
            .outerjoin(item_counts, item_counts.c.order_id == Order.id)
            .where(Order.user_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(RECENT)
        )
    ).all()
    addresses = (
        await db.execute(select(Address).where(Address.user_id == user.id).order_by(Address.created_at))
    ).scalars().all()

    vendor = (await db.execute(select(Vendor).where(Vendor.user_id == user.id))).scalar_one_or_none()
    courier = (await db.execute(select(Courier).where(Courier.user_id == user.id))).scalar_one_or_none()
    managed = (
        await db.execute(
            select(PickupPointManager, PickupPoint.name)
            .join(PickupPoint, PickupPoint.id == PickupPointManager.pickup_point_id)
            .where(PickupPointManager.user_id == user.id)
        )
    ).first()

    return AdminUserProfile(
        id=user.id,
        phone=user.phone,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        email_verified=user.email_verified,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        orders_count=count,
        orders_total=int(total),
        last_order_at=last,
        addresses=[
            ProfileAddress(label=a.label, zone=a.zone, delivery_type=a.delivery_type, is_default=a.is_default)
            for a in addresses
        ],
        recent_orders=[
            ProfileOrder(id=o.id, status=o.status, total=o.total, item_count=int(n or 0), created_at=o.created_at)
            for o, n in recent
        ],
        buyer_wallet=_wallet(await wallets_service.get_wallet_balance(db, AccountKind.BUYER, user.id)),
        vendor=ProfileVendorLink(id=vendor.id, shop_name=vendor.shop_name, status=vendor.status.value, zone=vendor.zone)
        if vendor
        else None,
        courier=ProfileCourierLink(
            id=courier.id, status=courier.status.value, vehicle_type=courier.vehicle_type.value, is_online=courier.is_online
        )
        if courier
        else None,
        managed_point=ProfileManagedPoint(manager_id=managed[0].id, pickup_point_id=managed[0].pickup_point_id, name=managed[1])
        if managed
        else None,
    )


async def update_user(db: AsyncSession, admin: User, user_id: uuid.UUID, data: AdminUserUpdate) -> AdminUserProfile:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Utilisateur introuvable.")
    fields = data.model_dump(exclude_unset=True)
    if fields.get("is_active") is False and user.id == admin.id:
        raise ConflictError("Vous ne pouvez pas désactiver votre propre compte.")
    if "email" in fields and fields["email"] and fields["email"] != user.email:
        taken = await db.scalar(select(func.count()).select_from(User).where(User.email == fields["email"], User.id != user.id))
        if taken:
            raise ConflictError("Cet email est déjà utilisé.")
        user.email_verified = False
    for key in ("first_name", "last_name"):
        if key in fields:
            fields[key] = (fields[key] or "").strip() or None
    for key, value in fields.items():
        setattr(user, key, value)
    await db.commit()
    return await user_profile(db, user_id)


# --- Livreur ----------------------------------------------------------------------


async def courier_profile(db: AsyncSession, courier_id: uuid.UUID) -> AdminCourierProfile:
    courier = await couriers_service.admin_get_courier(db, courier_id)
    user = await db.get(User, courier.user_id)
    since = datetime.now(UTC) - timedelta(days=30)
    rows = (
        await db.execute(
            select(SubOrder.status, func.count(), func.count().filter(SubOrder.updated_at >= since))
            .where(SubOrder.courier_id == courier.id)
            .group_by(SubOrder.status)
        )
    ).all()
    by_status = {status: (n, recent) for status, n, recent in rows}
    delivered, delivered_30d = by_status.get(OrderStatus.DELIVERED, (0, 0))
    in_progress = sum(
        by_status.get(s, (0, 0))[0]
        for s in (OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.SHIPPED, OrderStatus.ARRIVED_AT_PICKUP_POINT)
    )
    recent = (
        await db.execute(
            select(SubOrder, Order)
            .join(Order, Order.id == SubOrder.order_id)
            .where(SubOrder.courier_id == courier.id)
            .order_by(SubOrder.updated_at.desc())
            .limit(RECENT)
        )
    ).all()
    return AdminCourierProfile(
        courier=courier,
        email=user.email if user else None,
        user_is_active=user.is_active if user else False,
        created_at=courier.created_at,
        stats=DeliveryStats(
            delivered=delivered,
            in_progress=in_progress,
            cancelled=by_status.get(OrderStatus.CANCELLED, (0, 0))[0],
            delivered_30d=delivered_30d,
        ),
        wallet=_wallet(await wallets_service.get_wallet_balance(db, AccountKind.COURIER, courier.id)),
        recent_deliveries=[_delivery(so, o) for so, o in recent],
    )


# --- Point de retrait et gestionnaires ------------------------------------------------


async def _managers(db: AsyncSession, point_id: uuid.UUID | None = None) -> list[tuple[PickupPointManager, User]]:
    stmt = select(PickupPointManager, User).join(User, User.id == PickupPointManager.user_id)
    if point_id is not None:
        stmt = stmt.where(PickupPointManager.pickup_point_id == point_id)
    return list((await db.execute(stmt.order_by(PickupPointManager.created_at))).all())


def _manager_summary(manager: PickupPointManager, user: User) -> dict:
    return {
        "id": manager.id,
        "user_id": user.id,
        "phone": user.phone,
        "full_name": " ".join(filter(None, [user.first_name, user.last_name])) or None,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": manager.created_at,
    }


async def _point_parcel_counts(db: AsyncSession, point_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    since = datetime.now(UTC) - timedelta(days=30)
    rows = (
        await db.execute(
            select(
                Order.pickup_point_id,
                func.count().filter(SubOrder.status == OrderStatus.SHIPPED),
                func.count().filter(SubOrder.status == OrderStatus.ARRIVED_AT_PICKUP_POINT),
                func.count().filter(SubOrder.status == OrderStatus.DELIVERED),
                func.count().filter(SubOrder.status == OrderStatus.DELIVERED, SubOrder.updated_at >= since),
            )
            .join(Order, Order.id == SubOrder.order_id)
            .where(Order.pickup_point_id.in_(point_ids))
            .group_by(Order.pickup_point_id)
        )
    ).all()
    return {
        pid: {"expected": e, "in_stock": s, "delivered": d, "delivered_30d": d30} for pid, e, s, d, d30 in rows
    }


async def pickup_point_profile(db: AsyncSession, point_id: uuid.UUID) -> AdminPickupPointProfile:
    point = await pickup_points_service.admin_get_point(db, point_id)
    counts = (await _point_parcel_counts(db, [point.id])).get(
        point.id, {"expected": 0, "in_stock": 0, "delivered": 0, "delivered_30d": 0}
    )
    recent = (
        await db.execute(
            select(SubOrder, Order)
            .join(Order, Order.id == SubOrder.order_id)
            .where(Order.pickup_point_id == point.id)
            .order_by(SubOrder.updated_at.desc())
            .limit(RECENT)
        )
    ).all()
    return AdminPickupPointProfile(
        point=point,
        managers=[ManagerSummary(**_manager_summary(m, u)) for m, u in await _managers(db, point.id)],
        stats=PickupStats(**counts),
        wallet=_wallet(await wallets_service.get_wallet_balance(db, AccountKind.PICKUP_POINT, point.id)),
        recent_parcels=[_delivery(so, o) for so, o in recent],
    )


async def managers_overview(db: AsyncSession) -> list[AdminManagerOverview]:
    managers = await _managers(db)
    points = {
        p.id: p
        for p in (
            await db.execute(select(PickupPoint).where(PickupPoint.id.in_({m.pickup_point_id for m, _ in managers})))
        ).scalars()
    }
    counts = await _point_parcel_counts(db, list(points))
    result = []
    for manager, user in managers:
        point = points.get(manager.pickup_point_id)
        c = counts.get(manager.pickup_point_id, {})
        result.append(
            AdminManagerOverview(
                **_manager_summary(manager, user),
                pickup_point_id=manager.pickup_point_id,
                pickup_point_name=point.name if point else "—",
                pickup_point_is_active=point.is_active if point else False,
                parcels_in_stock=c.get("in_stock", 0),
                parcels_delivered=c.get("delivered", 0),
            )
        )
    return result
