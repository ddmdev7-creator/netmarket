"""Database access for Vendor."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from app.vendors.models import Vendor, VendorStatus


def _attach_user_fields(vendor: Vendor, user: User) -> Vendor:
    vendor.owner_phone = user.phone
    vendor.owner_email = user.email
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    vendor.owner_full_name = full_name or None
    return vendor


async def get_by_id(db: AsyncSession, vendor_id: uuid.UUID) -> Vendor | None:
    stmt = select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    vendor, user = row
    return _attach_user_fields(vendor, user)


async def get_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> Vendor | None:
    stmt = select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.user_id == user_id)
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    vendor, user = row
    return _attach_user_fields(vendor, user)


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    shop_name: str,
    zone: str | None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Vendor:
    vendor = Vendor(user_id=user_id, shop_name=shop_name, zone=zone, latitude=latitude, longitude=longitude)
    db.add(vendor)
    await db.flush()
    return vendor


async def list_by_status(db: AsyncSession, status: VendorStatus | None) -> list[Vendor]:
    stmt = select(Vendor, User).join(User, Vendor.user_id == User.id)
    if status is not None:
        stmt = stmt.where(Vendor.status == status)
    rows = (await db.execute(stmt.order_by(Vendor.created_at.desc()))).all()
    return [_attach_user_fields(vendor, user) for vendor, user in rows]


async def get_public_stats(db: AsyncSession, vendor_id: uuid.UUID) -> tuple[int, float | None, int]:
    """(produits actifs, note moyenne, nombre d'avis) sur l'ensemble de la boutique."""
    from app.catalog.models import Product, ProductStatus
    from app.reviews.models import Review

    product_count = (
        await db.execute(
            select(func.count())
            .select_from(Product)
            .where(Product.vendor_id == vendor_id, Product.status == ProductStatus.ACTIVE)
        )
    ).scalar_one()
    average, review_count = (
        await db.execute(
            select(func.avg(Review.rating), func.count(Review.id))
            .join(Product, Review.product_id == Product.id)
            .where(Product.vendor_id == vendor_id)
        )
    ).one()
    return product_count, (float(average) if average is not None else None), review_count
