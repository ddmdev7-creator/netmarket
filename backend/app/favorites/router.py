"""Favoris de l'acheteur connecté."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import Message
from app.core.deps import get_current_user, get_db
from app.favorites import service
from app.favorites.schemas import FavoriteIds, FavoriteRead
from app.users.models import User

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=list[FavoriteRead])
async def list_favorites(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[FavoriteRead]:
    return [FavoriteRead.model_validate(f, from_attributes=True) for f in await service.list_favorites(db, current_user)]


@router.get("/ids", response_model=FavoriteIds)
async def list_favorite_ids(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> FavoriteIds:
    return FavoriteIds(product_ids=await service.list_ids(db, current_user))


@router.put("/{product_id}", response_model=Message)
async def add_favorite(
    product_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Message:
    await service.add(db, current_user, product_id)
    return Message(detail="Ajouté aux favoris.")


@router.delete("/{product_id}", response_model=Message)
async def remove_favorite(
    product_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Message:
    await service.remove(db, current_user, product_id)
    return Message(detail="Retiré des favoris.")
