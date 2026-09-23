"""Pydantic schemas for product reviews."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewUpdate(ReviewCreate):
    """Remplace la note et le commentaire de son propre avis."""


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    user_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime
    # Prénom + initiale du nom (« Mamadou D. ») — jamais le nom complet ni le
    # téléphone sur une page publique. None si le compte n'a pas de prénom.
    author_name: str | None = None


class ReviewableProductRead(BaseModel):
    """Un produit que l'acheteur a reçu, avec son avis s'il en a déjà laissé
    un — alimente « Produits à noter » (GET /reviews/mine)."""

    product_id: uuid.UUID
    product_name: str
    product_image: str | None
    order_id: uuid.UUID
    delivered_at: datetime
    review: ReviewRead | None
