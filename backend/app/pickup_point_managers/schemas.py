"""Pydantic schemas for pickup point manager accounts (admin-only creation)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.auth.schemas import PHONE_PATTERN


class PickupPointManagerAdminCreate(BaseModel):
    """Admin-direct account creation — an admin creating the account IS the
    validation, same rationale as CourierAdminCreate, but there's no
    approval lifecycle to skip here since managers never self-register."""

    phone: str = Field(pattern=PHONE_PATTERN, description="Format international, ex: +224621234567")
    password: str = Field(min_length=8)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    pickup_point_id: uuid.UUID


class PickupPointManagerAdminUpdate(BaseModel):
    # Réassignation à un autre point — c'est la seule chose qu'un admin
    # ajuste après coup ; désactiver un gestionnaire se fait par suppression
    # (DELETE /admin/pickup-point-managers/{id}), pas un flag.
    pickup_point_id: uuid.UUID | None = None


class PickupPointManagerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    pickup_point_id: uuid.UUID
    # Attachés en lecture depuis User (voir app/pickup_point_managers/repository.py).
    phone: str
    full_name: str | None = None


class ManagerPointUpdate(BaseModel):
    opening_hours: str = Field(min_length=3, max_length=300)
