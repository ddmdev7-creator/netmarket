"""Business logic for admin-managed pickup points."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.pickup_points import repository
from app.pickup_points.models import PickupPoint
from app.pickup_points.schemas import PickupPointCreate, PickupPointUpdate
from app.vendors import repository as vendor_repository


async def _check_vendor_exists(db: AsyncSession, vendor_id: uuid.UUID | None) -> None:
    if vendor_id is not None and await vendor_repository.get_by_id(db, vendor_id) is None:
        raise NotFoundError("Boutique introuvable.")


async def create_point(db: AsyncSession, data: PickupPointCreate) -> PickupPoint:
    await _check_vendor_exists(db, data.vendor_id)
    point = await repository.create(db, **data.model_dump())
    await db.commit()
    return await repository.get_by_id(db, point.id)


async def list_public_points(db: AsyncSession) -> list[PickupPoint]:
    return await repository.list_active(db)


async def admin_list_points(db: AsyncSession) -> list[PickupPoint]:
    return await repository.list_all(db)


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
    return await repository.get_by_id(db, point_id)


async def delete_point(db: AsyncSession, point_id: uuid.UUID) -> None:
    point = await repository.get_by_id(db, point_id)
    if point is None:
        raise NotFoundError("Point de retrait introuvable.")
    await repository.delete(db, point)
    await db.commit()
