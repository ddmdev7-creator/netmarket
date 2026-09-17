"""Database access for Vendor."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.vendors.models import Vendor, VendorStatus


async def get_by_id(db: AsyncSession, vendor_id: uuid.UUID) -> Vendor | None:
    result = await db.execute(select(Vendor).where(Vendor.id == vendor_id))
    return result.scalar_one_or_none()


async def get_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> Vendor | None:
    result = await db.execute(select(Vendor).where(Vendor.user_id == user_id))
    return result.scalar_one_or_none()


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
    stmt = select(Vendor)
    if status is not None:
        stmt = stmt.where(Vendor.status == status)
    result = await db.execute(stmt.order_by(Vendor.created_at.desc()))
    return list(result.scalars().all())
