"""Pydantic schemas for admin-managed pickup points."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PickupPointCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    zone: str = Field(min_length=3, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_active: bool = True
    opening_hours: str | None = Field(default=None, max_length=300)
    # Renseigné quand ce point est la boutique d'un vendeur plutôt qu'un
    # local dédié — voir PickupPoint.vendor_id.
    vendor_id: uuid.UUID | None = None


class PickupPointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    zone: str | None = Field(default=None, min_length=3, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_active: bool | None = None
    opening_hours: str | None = Field(default=None, max_length=300)
    vendor_id: uuid.UUID | None = None


class PickupPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    zone: str
    latitude: float | None
    longitude: float | None
    is_active: bool
    vendor_id: uuid.UUID | None
    opening_hours: str | None = None
    # Attaché en lecture depuis Vendor (voir app/pickup_points/repository.py),
    # None si ce point n'est pas lié à une boutique.
    vendor_shop_name: str | None = None
    # Transitoires, calculés depuis pickup_point_reviews (voir
    # app/pickup_points/service.py::_attach_rating) — même motif que
    # Product.average_rating/review_count. None tant qu'aucun avis.
    average_rating: float | None = None
    review_count: int = 0


class PickupPointReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class PickupPointReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pickup_point_id: uuid.UUID
    user_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime
