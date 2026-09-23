"""Business logic for admin-managed pickup points."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.orders import repository as orders_repository
from app.pickup_points import repository
from app.pickup_points.models import PickupPoint, PickupPointReview
from app.pickup_points.schemas import PickupPointCreate, PickupPointReviewCreate, PickupPointUpdate
from app.users.models import User
from app.vendors import repository as vendor_repository


def _attach_rating(point: PickupPoint, summary: tuple[float, int] | None) -> PickupPoint:
    # Transient attributes, same pattern as app/catalog/service.py::_attach_rating.
    average, count = summary if summary is not None else (None, 0)
    point.average_rating = average
    point.review_count = count
    return point


async def _attach_ratings(db: AsyncSession, points: list[PickupPoint]) -> list[PickupPoint]:
    summaries = await repository.get_rating_summary_map(db, [p.id for p in points])
    return [_attach_rating(p, summaries.get(p.id)) for p in points]


async def _check_vendor_exists(db: AsyncSession, vendor_id: uuid.UUID | None) -> None:
    if vendor_id is not None and await vendor_repository.get_by_id(db, vendor_id) is None:
        raise NotFoundError("Boutique introuvable.")


async def create_point(db: AsyncSession, data: PickupPointCreate) -> PickupPoint:
    await _check_vendor_exists(db, data.vendor_id)
    point = await repository.create(db, **data.model_dump())
    await db.commit()
    return _attach_rating(await repository.get_by_id(db, point.id), None)


async def list_public_points(db: AsyncSession) -> list[PickupPoint]:
    points = await repository.list_active(db)
    return await _attach_ratings(db, points)


async def admin_list_points(db: AsyncSession) -> list[PickupPoint]:
    points = await repository.list_all(db)
    return await _attach_ratings(db, points)


async def update_point(db: AsyncSession, point_id: uuid.UUID, data: PickupPointUpdate) -> PickupPoint:
    point = await repository.get_by_id(db, point_id)
    if point is None:
        raise NotFoundError("Point de retrait introuvable.")

    fields = data.model_dump(exclude_unset=True)
    if "vendor_id" in fields:
        await _check_vendor_exists(db, fields["vendor_id"])
    for field, value in fields.items():
        setattr(point, field, value)

    await db.commit()
    summary = await repository.get_rating_summary(db, point_id)
    return _attach_rating(await repository.get_by_id(db, point_id), summary)


async def delete_point(db: AsyncSession, point_id: uuid.UUID) -> None:
    point = await repository.get_by_id(db, point_id)
    if point is None:
        raise NotFoundError("Point de retrait introuvable.")
    await repository.delete(db, point)
    await db.commit()


async def create_review(
    db: AsyncSession, user: User, pickup_point_id: uuid.UUID, data: PickupPointReviewCreate
) -> PickupPointReview:
    if not await orders_repository.has_used_pickup_point_for_user(db, user.id, pickup_point_id):
        raise ForbiddenError("Vous ne pouvez noter qu'un point de retrait que vous avez déjà utilisé.")
    if await repository.get_review_by_point_and_user(db, pickup_point_id, user.id) is not None:
        raise ConflictError("Vous avez déjà noté ce point de retrait.")

    review = await repository.create_review(
        db, pickup_point_id=pickup_point_id, user_id=user.id, rating=data.rating, comment=data.comment
    )
    await db.commit()
    await db.refresh(review)
    return review
