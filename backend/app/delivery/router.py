"""Admin endpoints for the delivery fee grid (distance tiers)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import Message
from app.core.deps import get_db, require_role
from app.delivery import service
from app.delivery.schemas import DeliveryFeeTierCreate, DeliveryFeeTierRead, DeliveryFeeTierUpdate
from app.users.models import UserRole

admin_router = APIRouter(
    prefix="/admin/delivery-fee-tiers", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@admin_router.get("", response_model=list[DeliveryFeeTierRead])
async def admin_list_tiers(db: AsyncSession = Depends(get_db)) -> list[DeliveryFeeTierRead]:
    return await service.list_tiers(db)


@admin_router.post("", response_model=DeliveryFeeTierRead, status_code=status.HTTP_201_CREATED)
async def admin_create_tier(payload: DeliveryFeeTierCreate, db: AsyncSession = Depends(get_db)) -> DeliveryFeeTierRead:
    return await service.create_tier(db, payload)


@admin_router.patch("/{tier_id}", response_model=DeliveryFeeTierRead)
async def admin_update_tier(
    tier_id: uuid.UUID, payload: DeliveryFeeTierUpdate, db: AsyncSession = Depends(get_db)
) -> DeliveryFeeTierRead:
    return await service.update_tier(db, tier_id, payload)


@admin_router.delete("/{tier_id}", response_model=Message)
async def admin_delete_tier(tier_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Message:
    await service.delete_tier(db, tier_id)
    return Message(detail="Palier supprimé.")
