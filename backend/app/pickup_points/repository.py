"""Database access for pickup points."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pickup_points.models import PickupPoint
from app.vendors.models import Vendor


def _attach_vendor_shop_name(point: PickupPoint, shop_name: str | None) -> PickupPoint:
    point.vendor_shop_name = shop_name
    return point


async def create(db: AsyncSession, **fields) -> PickupPoint:
    point = PickupPoint(**fields)
    db.add(point)
    await db.flush()
    return point


async def get_by_id(db: AsyncSession, point_id: uuid.UUID) -> PickupPoint | None:
    stmt = (
        select(PickupPoint, Vendor.shop_name)
        .outerjoin(Vendor, PickupPoint.vendor_id == Vendor.id)
        .where(PickupPoint.id == point_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    point, shop_name = row
    return _attach_vendor_shop_name(point, shop_name)


async def list_active(db: AsyncSession) -> list[PickupPoint]:
    stmt = (
        select(PickupPoint, Vendor.shop_name)
        .outerjoin(Vendor, PickupPoint.vendor_id == Vendor.id)
        .where(PickupPoint.is_active.is_(True))
        .order_by(PickupPoint.name)
    )
    rows = (await db.execute(stmt)).all()
    return [_attach_vendor_shop_name(point, shop_name) for point, shop_name in rows]


async def list_all(db: AsyncSession) -> list[PickupPoint]:
    stmt = select(PickupPoint, Vendor.shop_name).outerjoin(Vendor, PickupPoint.vendor_id == Vendor.id).order_by(PickupPoint.name)
    rows = (await db.execute(stmt)).all()
    return [_attach_vendor_shop_name(point, shop_name) for point, shop_name in rows]


async def delete(db: AsyncSession, point: PickupPoint) -> None:
    await db.delete(point)
