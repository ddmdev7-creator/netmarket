"""Product review endpoints, nested under /products/{product_id}/reviews,
plus the buyer's own "products to review" list under /reviews/mine."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.reviews import service
from app.reviews.schemas import ReviewableProductRead, ReviewCreate, ReviewRead, ReviewUpdate
from app.users.models import User

router = APIRouter(prefix="/products/{product_id}/reviews", tags=["reviews"])
me_router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review(
    product_id: uuid.UUID,
    payload: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewRead:
    return await service.create_review(db, current_user, product_id, payload)


@router.put("/mine", response_model=ReviewRead)
async def update_my_review(
    product_id: uuid.UUID,
    payload: ReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewRead:
    return await service.update_my_review(db, current_user, product_id, payload)


@router.get("", response_model=list[ReviewRead])
async def list_reviews(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ReviewRead]:
    return await service.list_reviews_for_product(db, product_id)


@me_router.get("/mine", response_model=list[ReviewableProductRead])
async def list_my_reviewable_products(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ReviewableProductRead]:
    """Produits reçus par l'acheteur connecté, notés ou non."""
    return await service.list_reviewable_products(db, current_user)
