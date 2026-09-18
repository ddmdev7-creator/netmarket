"""Pydantic schemas for admin-managed pickup points."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class PickupPointCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    zone: str = Field(min_length=3, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_active: bool = True
    # Renseigné quand ce point est la boutique d'un vendeur plutôt qu'un
    # local dédié — voir PickupPoint.vendor_id.
    vendor_id: uuid.UUID | None = None


class PickupPointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    zone: str | None = Field(default=None, min_length=3, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_active: bool | None = None
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
    # Attaché en lecture depuis Vendor (voir app/pickup_points/repository.py),
    # None si ce point n'est pas lié à une boutique.
    vendor_shop_name: str | None = None
