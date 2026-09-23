"""Database access for pickup points."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pickup_points.models import PickupPoint, PickupPointReview
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


async def get_review_by_point_and_user(
    db: AsyncSession, pickup_point_id: uuid.UUID, user_id: uuid.UUID
) -> PickupPointReview | None:
    result = await db.execute(
        select(PickupPointReview).where(
            PickupPointReview.pickup_point_id == pickup_point_id, PickupPointReview.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def create_review(
    db: AsyncSession, *, pickup_point_id: uuid.UUID, user_id: uuid.UUID, rating: int, comment: str | None
) -> PickupPointReview:
    review = PickupPointReview(pickup_point_id=pickup_point_id, user_id=user_id, rating=rating, comment=comment)
    db.add(review)
    await db.flush()
    return review


async def get_rating_summary(db: AsyncSession, pickup_point_id: uuid.UUID) -> tuple[float | None, int]:
    stmt = select(func.avg(PickupPointReview.rating), func.count(PickupPointReview.id)).where(
        PickupPointReview.pickup_point_id == pickup_point_id
    )
    average, count = (await db.execute(stmt)).one()
    return (float(average) if average is not None else None, count)


async def get_rating_summary_map(
    db: AsyncSession, pickup_point_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[float, int]]:
    if not pickup_point_ids:
        return {}
    stmt = (
        select(PickupPointReview.pickup_point_id, func.avg(PickupPointReview.rating), func.count(PickupPointReview.id))
        .where(PickupPointReview.pickup_point_id.in_(pickup_point_ids))
        .group_by(PickupPointReview.pickup_point_id)
    )
    rows = (await db.execute(stmt)).all()
    return {pickup_point_id: (float(average), count) for pickup_point_id, average, count in rows}
