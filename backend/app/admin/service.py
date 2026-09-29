"""Compose aggregate queries into the admin dashboard payload."""

import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import repository
from app.admin.schemas import (
    AdminAttention,
    RouteRead,
    ActiveDeliveryRead,
    AdminStats,
    DailyActivity,
    DeliveryMonitorEntry,
    DeliveryMonitorRead,
    TopProduct,
    TopVendor,
)
from app.core.exceptions import NotFoundError
from app.core.pagination import PageParams
from app.couriers import repository as couriers_repository
from app.orders import repository as orders_repository
from app.orders import service as orders_service
from app.orders import tracking
from app.orders.models import DeliveryType, Order, OrderStatus
from app.orders.schemas import AdminBuyerInfo, AdminCourierInfo, AdminPickupPointInfo, AdminVendorInfo
from app.payments import repository as payments_repository
from app.pickup_points import repository as pickup_points_repository
from app.routing import service as routing_service
from app.users import repository as users_repository


# Fenêtre des courbes du tableau de bord admin.
DASHBOARD_DAYS = 30


async def get_stats(db: AsyncSession) -> AdminStats:
    vendor_counts = await repository.count_vendors_by_status(db)
    order_counts = await repository.count_orders_by_status(db)
    total_products = await repository.count_products(db)
    total_sales, total_commission = await repository.sum_sales_and_commission(db)
    top_products_rows = await repository.top_products(db)
    top_vendors_rows = await repository.top_vendors(db)
    today = datetime.now(UTC).date()
    first_day = today - timedelta(days=DASHBOARD_DAYS - 1)
    since = datetime.combine(first_day, time.min, tzinfo=UTC)
    orders_per_day = await repository.daily_orders(db, since)
    signups_per_day = await repository.daily_signups(db, since)

    return AdminStats(
        total_vendors=sum(vendor_counts.values()),
        pending_vendors=vendor_counts["pending"],
        approved_vendors=vendor_counts["approved"],
        total_products=total_products,
        total_orders=sum(order_counts.values()),
        orders_by_status=order_counts,
        total_sales=total_sales,
        total_commission=total_commission,
        top_products=[
            TopProduct(product_id=product_id, product_name=name, quantity_sold=int(qty))
            for product_id, name, qty in top_products_rows
        ],
        top_vendors=[
            TopVendor(vendor_id=vendor_id, shop_name=name, revenue=int(revenue))
            for vendor_id, name, revenue in top_vendors_rows
        ],
        daily_activity=[
            DailyActivity(
                date=day,
                orders=orders_per_day.get(day, (0, 0))[0],
                order_amount=orders_per_day.get(day, (0, 0))[1],
                signups=signups_per_day.get(day, 0),
            )
            for day in (first_day + timedelta(days=i) for i in range(DASHBOARD_DAYS))
        ],
        orders_by_payment_method=await repository.count_orders_by_payment_method(db),
        users_by_role=await repository.count_users_by_role(db),
    )


async def list_orders(
    db: AsyncSession, params: PageParams, status_filter: OrderStatus | None
) -> tuple[list[Order], int]:
    items, total = await repository.list_all_orders(db, params, status_filter)
    for order in items:
        for sub_order in order.sub_orders:
            await orders_service._attach_product_images(db, sub_order)
    return items, total


def _full_name(first: str | None, last: str | None) -> str | None:
    return " ".join(part for part in (first, last) if part) or None


async def _courier_info(db: AsyncSession, courier_id: uuid.UUID | None) -> AdminCourierInfo | None:
    if courier_id is None:
        return None
    courier = await couriers_repository.get_by_id(db, courier_id)
    if courier is None:
        return None
    average, count = await couriers_repository.get_rating_summary(db, courier.id)
    info = AdminCourierInfo.model_validate(courier)
    info.average_rating, info.review_count = average, count
    return info


async def _vendor_info(db: AsyncSession, vendor_id: uuid.UUID) -> AdminVendorInfo | None:
    row = await repository.get_vendor_with_owner(db, vendor_id)
    if row is None:
        return None
    vendor, owner = row
    return AdminVendorInfo(
        id=vendor.id,
        shop_name=vendor.shop_name,
        status=vendor.status,
        zone=vendor.zone,
        latitude=vendor.latitude,
        longitude=vendor.longitude,
        commission_rate=float(vendor.commission_rate),
        preparation_days=vendor.preparation_days,
        created_at=vendor.created_at,
        owner_full_name=_full_name(owner.first_name, owner.last_name),
        owner_phone=owner.phone,
        owner_email=owner.email,
    )


async def _pickup_point_info(db: AsyncSession, pickup_point_id: uuid.UUID | None) -> AdminPickupPointInfo | None:
    if pickup_point_id is None:
        return None
    row = await repository.get_pickup_point_with_shop(db, pickup_point_id)
    if row is None:
        return None
    point, shop_name = row
    average, count = await pickup_points_repository.get_rating_summary(db, point.id)
    return AdminPickupPointInfo(
        id=point.id,
        name=point.name,
        zone=point.zone,
        latitude=point.latitude,
        longitude=point.longitude,
        is_active=point.is_active,
        vendor_shop_name=shop_name,
        average_rating=average,
        review_count=count,
    )


async def get_order_detail(db: AsyncSession, order_id: uuid.UUID) -> Order:
    order = await orders_repository.get_order_by_id(db, order_id)
    if order is None:
        raise NotFoundError("Commande introuvable.")

    buyer = await users_repository.get_by_id(db, order.user_id)
    order.buyer = (
        AdminBuyerInfo(
            id=buyer.id,
            full_name=_full_name(buyer.first_name, buyer.last_name),
            phone=buyer.phone,
            email=buyer.email,
            email_verified=buyer.email_verified,
            is_active=buyer.is_active,
            created_at=buyer.created_at,
            order_count=await repository.count_orders_for_user(db, buyer.id),
        )
        if buyer
        else None
    )

    payment = await payments_repository.get_by_order_id(db, order.id)
    order.payment_status = payment.status if payment else None
    await orders_service._attach_pickup_point_contacts(db, order, order.pickup_point_id)
    order.pickup_point = await _pickup_point_info(db, order.pickup_point_id)

    vendors: dict[uuid.UUID, AdminVendorInfo | None] = {}
    for sub_order in order.sub_orders:
        await orders_service._attach_product_images(db, sub_order)
        await orders_service._attach_dispatch_offer_info(db, sub_order)
        sub_order.courier = await _courier_info(db, sub_order.courier_id)
        if sub_order.vendor_id not in vendors:
            vendors[sub_order.vendor_id] = await _vendor_info(db, sub_order.vendor_id)
        sub_order.vendor = vendors[sub_order.vendor_id]

    return order


async def get_delivery_monitor(db: AsyncSession, *, with_routes: bool = False) -> DeliveryMonitorRead:
    now = datetime.now(UTC)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await repository.list_monitored_deliveries(db, since)

    courier_ids = {
        courier_id
        for sub_order, *_ in rows
        for courier_id in (sub_order.courier_id, sub_order.dispatch_offered_courier_id)
        if courier_id is not None
    }
    couriers = {c.id: c for c in await couriers_repository.list_by_ids(db, courier_ids)}

    def courier_name(courier_id: uuid.UUID | None) -> str | None:
        courier = couriers.get(courier_id) if courier_id else None
        return (courier.full_name or courier.phone) if courier else None

    entries = []
    for (
        sub_order,
        order,
        buyer,
        vendor_zone,
        pickup_point_name,
        vendor_lat,
        vendor_lng,
        point_lat,
        point_lng,
    ) in rows:
        courier = couriers.get(sub_order.courier_id) if sub_order.courier_id else None
        is_pickup = order.delivery_type == DeliveryType.PICKUP_POINT
        live = bool(
            courier
            and sub_order.status == OrderStatus.SHIPPED
            and courier.position_updated_at
            and courier.latitude is not None
            and now - courier.position_updated_at <= tracking.POSITION_MAX_AGE
        )
        entries.append(
            DeliveryMonitorEntry(
                sub_order_id=sub_order.id,
                order_id=order.id,
                status=sub_order.status,
                created_at=sub_order.created_at,
                updated_at=sub_order.updated_at,
                estimated_delivery_min=sub_order.estimated_delivery_min,
                estimated_delivery_max=sub_order.estimated_delivery_max,
                amount=sub_order.amount,
                delivery_fee=sub_order.delivery_fee,
                payment_method=order.payment_method,
                vendor_id=sub_order.vendor_id,
                shop_name=sub_order.shop_name,
                vendor_zone=vendor_zone,
                delivery_type=order.delivery_type,
                delivery_zone=order.delivery_zone,
                delivery_address=order.delivery_address,
                pickup_point_name=pickup_point_name,
                storage_location=sub_order.storage_location,
                # Le destinataire saisi au checkout prime sur le titulaire du compte.
                buyer_name=order.recipient_name
                or (_full_name(buyer.first_name, buyer.last_name) if buyer else None),
                buyer_phone=order.recipient_phone or (buyer.phone if buyer else None),
                courier_id=sub_order.courier_id,
                courier_name=courier_name(sub_order.courier_id),
                courier_phone=courier.phone if courier else None,
                courier_is_online=courier.is_online if courier else None,
                dispatch_offered_courier_id=sub_order.dispatch_offered_courier_id,
                dispatch_offered_courier_name=courier_name(sub_order.dispatch_offered_courier_id),
                origin_latitude=vendor_lat,
                origin_longitude=vendor_lng,
                destination_latitude=point_lat if is_pickup else order.delivery_latitude,
                destination_longitude=point_lng if is_pickup else order.delivery_longitude,
                courier_latitude=courier.latitude if live else None,
                courier_longitude=courier.longitude if live else None,
                courier_position_at=courier.position_updated_at if live else None,
                courier_live=live,
            )
        )
    if with_routes:
        await _attach_routes(entries)
    return DeliveryMonitorRead(generated_at=now, since=since, entries=entries)


async def _attach_routes(entries: list[DeliveryMonitorEntry]) -> None:
    """Trajet de chaque livraison en cours : livreur → destination quand sa
    position est connue en direct, sinon boutique → destination."""
    semaphore = asyncio.Semaphore(4)

    async def one(entry: DeliveryMonitorEntry) -> None:
        if entry.status == OrderStatus.DELIVERED or entry.destination_latitude is None:
            return
        start = (
            (entry.courier_latitude, entry.courier_longitude)
            if entry.courier_live
            else (entry.origin_latitude, entry.origin_longitude)
        )
        if start[0] is None:
            return
        async with semaphore:
            route = await routing_service.get_route([start, (entry.destination_latitude, entry.destination_longitude)])
        if route:
            entry.route = RouteRead(**route)

    await asyncio.gather(*(one(e) for e in entries))


async def list_active_deliveries(db: AsyncSession) -> list[ActiveDeliveryRead]:
    return [
        ActiveDeliveryRead(
            sub_order_id=sub_order.id,
            order_id=order.id,
            status=sub_order.status,
            vendor_id=sub_order.vendor_id,
            shop_name=sub_order.shop_name,
            created_at=sub_order.created_at,
            origin_latitude=vendor_lat,
            origin_longitude=vendor_lng,
            delivery_type=order.delivery_type,
            delivery_zone=order.delivery_zone,
            delivery_address=order.delivery_address,
            pickup_point_name=pickup_point_name,
            destination_latitude=order.delivery_latitude,
            destination_longitude=order.delivery_longitude,
            courier_id=sub_order.courier_id,
            dispatch_offered_courier_id=sub_order.dispatch_offered_courier_id,
        )
        for sub_order, order, vendor_lat, vendor_lng, pickup_point_name in await repository.list_active_deliveries(db)
    ]


async def get_attention(db: AsyncSession) -> AdminAttention:
    from sqlalchemy import func, select

    from app.couriers.models import Courier, CourierStatus
    from app.orders.models import SubOrder
    from app.payments.models import Payment, PaymentStatus
    from app.pickup_point_applications.models import ApplicationStatus, PickupPointApplication
    from app.reports.models import Report, ReportStatus
    from app.vendors.models import Vendor, VendorStatus
    from app.wallets.models import Withdrawal, WithdrawalStatus

    async def count(model, *conditions) -> int:
        return (await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()

    return AdminAttention(
        pending_vendors=await count(Vendor, Vendor.status == VendorStatus.PENDING),
        pending_couriers=await count(Courier, Courier.status == CourierStatus.PENDING),
        pending_applications=await count(
            PickupPointApplication, PickupPointApplication.status == ApplicationStatus.SUBMITTED
        ),
        pending_reports=await count(Report, Report.status == ReportStatus.PENDING),
        pending_withdrawals=await count(Withdrawal, Withdrawal.status == WithdrawalStatus.PENDING),
        pending_orders=await count(SubOrder, SubOrder.status == OrderStatus.PENDING),
        unassigned_deliveries=await count(
            SubOrder,
            SubOrder.status.in_((OrderStatus.CONFIRMED, OrderStatus.PREPARING)),
            SubOrder.courier_id.is_(None),
        ),
        failed_refunds=await count(Payment, Payment.status == PaymentStatus.REFUND_FAILED),
    )
