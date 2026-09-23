"""Pickup point endpoints: public read-only listing (for buyers choosing an
address) plus full admin CRUD under /admin/pickup-points."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import Message
from app.core.deps import get_current_user, get_db, require_role
from app.pickup_point_managers import service as pickup_point_managers_service
from app.pickup_point_managers.schemas import PickupPointManagerRead
from app.pickup_points import service
from app.pickup_points.schemas import (
    PickupPointCreate,
    PickupPointRead,
    PickupPointReviewCreate,
    PickupPointReviewRead,
    PickupPointUpdate,
)
from app.users.models import User, UserRole

router = APIRouter(prefix="/pickup-points", tags=["pickup-points"])
admin_router = APIRouter(
    prefix="/admin/pickup-points", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.get("", response_model=list[PickupPointRead])
async def list_pickup_points(db: AsyncSession = Depends(get_db)) -> list[PickupPointRead]:
    return await service.list_public_points(db)


@router.post("/{point_id}/reviews", response_model=PickupPointReviewRead, status_code=status.HTTP_201_CREATED)
async def create_pickup_point_review(
    point_id: uuid.UUID,
    payload: PickupPointReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PickupPointReviewRead:
    return await service.create_review(db, current_user, point_id, payload)


@admin_router.get("", response_model=list[PickupPointRead])
async def admin_list_pickup_points(db: AsyncSession = Depends(get_db)) -> list[PickupPointRead]:
    return await service.admin_list_points(db)


@admin_router.post("", response_model=PickupPointRead, status_code=status.HTTP_201_CREATED)
async def admin_create_pickup_point(
    payload: PickupPointCreate, db: AsyncSession = Depends(get_db)
) -> PickupPointRead:
    return await service.create_point(db, payload)


@admin_router.patch("/{point_id}", response_model=PickupPointRead)
async def admin_update_pickup_point(
    point_id: uuid.UUID, payload: PickupPointUpdate, db: AsyncSession = Depends(get_db)
) -> PickupPointRead:
    return await service.update_point(db, point_id, payload)


@admin_router.delete("/{point_id}", response_model=Message)
async def admin_delete_pickup_point(point_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Message:
    await service.delete_point(db, point_id)
    return Message(detail="Point de retrait supprimé.")


@admin_router.post(
    "/{point_id}/link-vendor-manager", response_model=PickupPointManagerRead, status_code=status.HTTP_201_CREATED
)
async def admin_link_vendor_as_manager(
    point_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> PickupPointManagerRead:
    return await pickup_point_managers_service.admin_link_vendor_as_manager(db, point_id)
