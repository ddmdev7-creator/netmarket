"""Pickup point manager endpoints: admin-only account creation/management,
plus a self-lookup endpoint the manager's own dashboard uses to resolve
"which point am I managing"."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import Message
from app.core.deps import get_db, get_pickup_point_manager, require_role
from app.pickup_point_managers import service
from app.pickup_point_managers.schemas import (
    ManagerPointUpdate,
    PickupPointManagerAdminCreate,
    PickupPointManagerAdminUpdate,
    PickupPointManagerRead,
)
from app.pickup_points.schemas import PickupPointRead
from app.users.models import User, UserRole

router = APIRouter(prefix="/pickup-point-managers", tags=["pickup-point-managers"])
admin_router = APIRouter(
    prefix="/admin/pickup-point-managers", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.get("/me/point", response_model=PickupPointRead)
async def get_my_point(
    current_user: User = Depends(get_pickup_point_manager), db: AsyncSession = Depends(get_db)
) -> PickupPointRead:
    """Le point de retrait géré : nom, adresse, horaires, note moyenne."""
    return await service.get_my_point(db, current_user)


@router.patch("/me/point", response_model=PickupPointRead)
async def update_my_point(
    payload: ManagerPointUpdate,
    current_user: User = Depends(get_pickup_point_manager),
    db: AsyncSession = Depends(get_db),
) -> PickupPointRead:
    """Le gestionnaire met à jour les horaires affichés aux clients."""
    return await service.update_my_point(db, current_user, payload)


@router.get("/me", response_model=PickupPointManagerRead)
async def get_my_manager(
    current_user: User = Depends(get_pickup_point_manager), db: AsyncSession = Depends(get_db)
) -> PickupPointManagerRead:
    return await service.get_my_manager_profile(db, current_user)


@admin_router.post("", response_model=PickupPointManagerRead, status_code=status.HTTP_201_CREATED)
async def admin_create_manager(
    payload: PickupPointManagerAdminCreate, db: AsyncSession = Depends(get_db)
) -> PickupPointManagerRead:
    return await service.admin_create_manager(db, payload)


@admin_router.get("", response_model=list[PickupPointManagerRead])
async def admin_list_managers(
    pickup_point_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PickupPointManagerRead]:
    return await service.admin_list_managers(db, pickup_point_id)


@admin_router.patch("/{manager_id}", response_model=PickupPointManagerRead)
async def admin_update_manager(
    manager_id: uuid.UUID, payload: PickupPointManagerAdminUpdate, db: AsyncSession = Depends(get_db)
) -> PickupPointManagerRead:
    return await service.admin_update_manager(db, manager_id, payload)


@admin_router.delete("/{manager_id}", response_model=Message)
async def admin_delete_manager(manager_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Message:
    await service.admin_delete_manager(db, manager_id)
    return Message(detail="Gestionnaire supprimé.")
