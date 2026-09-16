"""Database access for User. Also used by the auth module (registration/login)."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address
from app.cart.models import CartItem
from app.catalog.models import Product
from app.couriers.models import Courier
from app.orders.models import Order, OrderItem, SubOrder
from app.payments.models import Payment
from app.pickup_point_managers.models import PickupPointManager
from app.reports.models import Report
from app.reviews.models import Review
from app.subscriptions.models import VendorSubscription
from app.users.models import EmailVerificationCode, User, UserRole
from app.vendors.models import Vendor


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_all(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.role, User.created_at))
    return list(result.scalars().all())


async def get_by_phone(db: AsyncSession, phone: str) -> User | None:
    result = await db.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    phone: str,
    password_hash: str,
    role: UserRole,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    user = User(
        phone=phone,
        password_hash=password_hash,
        role=role,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )
    db.add(user)
    await db.flush()
    return user


async def get_verification_code(db: AsyncSession, user_id: uuid.UUID) -> EmailVerificationCode | None:
    result = await db.execute(select(EmailVerificationCode).where(EmailVerificationCode.user_id == user_id))
    return result.scalar_one_or_none()


async def put_verification_code(
    db: AsyncSession, user_id: uuid.UUID, *, code_hash: str, expires_at: datetime
) -> EmailVerificationCode:
    """Replace whatever code this user currently has (register, or a resend) with a fresh one."""
    existing = await get_verification_code(db, user_id)
    if existing is not None:
        await db.delete(existing)
        await db.flush()
    record = EmailVerificationCode(user_id=user_id, code_hash=code_hash, expires_at=expires_at)
    db.add(record)
    await db.flush()
    return record


async def delete_verification_code(db: AsyncSession, record: EmailVerificationCode) -> None:
    await db.delete(record)


async def purge_user(db: AsyncSession, user: User) -> None:
    """Delete a user and everything that references them, in FK-safe order.

    Cross-module by nature — a user can be a vendor with a shop and orders,
    a buyer with their own order history, a courier assigned to deliveries,
    etc. — so this reaches into every module with a foreign key to users.id
    (or transitively to a vendor/product owned by this user) that isn't
    already ON DELETE CASCADE at the DB level. Notifications are the one
    exception, already cascading via the DB (see app/notifications/models.py:
    user_id/order_id/sub_order_id all have ondelete="CASCADE").
    """
    vendor = (await db.execute(select(Vendor).where(Vendor.user_id == user.id))).scalar_one_or_none()
    if vendor is not None:
        product_ids = select(Product.id).where(Product.vendor_id == vendor.id)
        vendor_sub_order_ids = select(SubOrder.id).where(SubOrder.vendor_id == vendor.id)

        await db.execute(delete(OrderItem).where(OrderItem.sub_order_id.in_(vendor_sub_order_ids)))
        await db.execute(delete(SubOrder).where(SubOrder.vendor_id == vendor.id))
        await db.execute(delete(Review).where(Review.product_id.in_(product_ids)))
        await db.execute(delete(CartItem).where(CartItem.product_id.in_(product_ids)))
        await db.execute(delete(VendorSubscription).where(VendorSubscription.vendor_id == vendor.id))
        await db.execute(delete(Product).where(Product.vendor_id == vendor.id))
        await db.execute(delete(Vendor).where(Vendor.id == vendor.id))

    courier = (await db.execute(select(Courier).where(Courier.user_id == user.id))).scalar_one_or_none()
    if courier is not None:
        # Nullable FKs on SubOrder — free the courier from any in-flight
        # dispatch before removing the row, rather than deleting the
        # sub-order itself (it may belong to a buyer/vendor being kept).
        await db.execute(update(SubOrder).where(SubOrder.courier_id == courier.id).values(courier_id=None))
        await db.execute(
            update(SubOrder)
            .where(SubOrder.dispatch_offered_courier_id == courier.id)
            .values(dispatch_offered_courier_id=None)
        )
        await db.execute(delete(Courier).where(Courier.id == courier.id))

    await db.execute(delete(PickupPointManager).where(PickupPointManager.user_id == user.id))

    own_order_ids = select(Order.id).where(Order.user_id == user.id)
    own_sub_order_ids = select(SubOrder.id).where(SubOrder.order_id.in_(own_order_ids))
    await db.execute(delete(OrderItem).where(OrderItem.sub_order_id.in_(own_sub_order_ids)))
    await db.execute(delete(Payment).where(Payment.order_id.in_(own_order_ids)))
    await db.execute(delete(SubOrder).where(SubOrder.order_id.in_(own_order_ids)))
    await db.execute(delete(Order).where(Order.user_id == user.id))

    await db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    await db.execute(delete(Review).where(Review.user_id == user.id))
    await db.execute(delete(Report).where(Report.reporter_id == user.id))
    await db.execute(delete(Address).where(Address.user_id == user.id))
    await db.execute(delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id))

    await db.delete(user)
