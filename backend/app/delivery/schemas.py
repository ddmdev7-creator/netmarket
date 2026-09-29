"""Pydantic schemas for the delivery fee grid and the checkout quote."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class DeliveryFeeTierCreate(BaseModel):
    # None = palier "au-delà" (et repli quand la distance est inconnue).
    max_km: float | None = Field(default=None, gt=0, le=1000)
    fee: int = Field(ge=0, le=10_000_000)
    label: str | None = Field(default=None, max_length=100)
    # Jours de trajet ajoutés à la préparation du vendeur pour ce palier.
    transit_days: int = Field(default=1, ge=0, le=30)
    # Palier appliqué quand la position de l'acheteur est inconnue.
    is_default: bool = False


class DeliveryFeeTierUpdate(BaseModel):
    # max_km peut être remis à None (devenir le palier "au-delà"), d'où
    # l'usage de exclude_unset côté service.
    max_km: float | None = Field(default=None, gt=0, le=1000)
    fee: int | None = Field(default=None, ge=0, le=10_000_000)
    label: str | None = Field(default=None, max_length=100)
    transit_days: int | None = Field(default=None, ge=0, le=30)
    is_default: bool | None = None


class DeliveryFeeTierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    max_km: float | None
    fee: int
    label: str | None
    transit_days: int
    is_default: bool = False
