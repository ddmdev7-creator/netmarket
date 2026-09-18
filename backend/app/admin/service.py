"""Compose aggregate queries into the admin dashboard payload."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import repository
from app.admin.schemas import AdminStats, TopProduct, TopVendor
from app.core.exceptions import NotFoundError
from app.core.pagination import PageParams
from app.orders import repository as orders_repository
from app.orders import service as orders_service
from app.orders.models import Order, OrderStatus
from app.payments import repository as payments_repository
from app.users import repository as users_repository


async def get_stats(db: AsyncSession) -> AdminStats:
    vendor_counts = await repository.count_vendors_by_status(db)
    order_counts = await repository.count_orders_by_status(db)
    total_products = await repository.count_products(db)
    total_sales, total_commission = await repository.sum_sales_and_commission(db)
    top_products_rows = await repository.top_products(db)
    top_vendors_rows = await repository.top_vendors(db)

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


async def get_order_detail(db: AsyncSession, order_id: uuid.UUID) -> Order:
    order = await orders_repository.get_order_by_id(db, order_id)
    if order is None:
        raise NotFoundError("Commande introuvable.")

    buyer = await users_repository.get_by_id(db, order.user_id)
    order.buyer_phone = buyer.phone if buyer else ""
    order.buyer_email = buyer.email if buyer else None
    order.buyer_full_name = _full_name(buyer.first_name, buyer.last_name) if buyer else None

    payment = await payments_repository.get_by_order_id(db, order.id)
    order.payment_status = payment.status if payment else None
    await orders_service._attach_pickup_point_contacts(db, order, order.pickup_point_id)

    for sub_order in order.sub_orders:
        await orders_service._attach_product_images(db, sub_order)
        await orders_service._attach_courier_info(db, sub_order)
        owner = await repository.get_vendor_owner(db, sub_order.vendor_id)
        sub_order.vendor_owner_phone = owner.phone if owner else None
        sub_order.vendor_owner_email = owner.email if owner else None
        sub_order.vendor_owner_full_name = _full_name(owner.first_name, owner.last_name) if owner else None

    return order
