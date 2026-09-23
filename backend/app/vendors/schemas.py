"""Pydantic schemas for vendor onboarding, profile and admin validation."""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.vendors.models import VendorStatus


class VendorRegister(BaseModel):
    shop_name: str = Field(min_length=2, max_length=150)
    zone: str | None = Field(default=None, max_length=150)
    # Email is optional at buyer registration but required to become a
    # vendor — see app/vendors/service.py::register_vendor, which uses it to
    # send the verification code gating access to the vendor dashboard.
    email: EmailStr
    # Position de la boutique, obligatoire dès l'inscription : elle sert à
    # calculer les frais et le délai de livraison (app/delivery/service.py::
    # compute_fee et compute_transit_days) et à trier les livreurs candidats
    # par distance (app/orders/service.py::start_dispatch). Sans elle, la
    # boutique retombe sur le palier de repli (le plus cher, le plus lent).
    # Les boutiques créées avant cette règle peuvent rester sans position
    # (colonne nullable).
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class VendorOwnerUpdate(BaseModel):
    shop_name: str | None = Field(default=None, min_length=2, max_length=150)
    zone: str | None = Field(default=None, max_length=150)
    # Une position existante ne peut pas être effacée : null est ignoré (voir
    # service.update_my_vendor), ce qui laisse une boutique sans position
    # (créée avant la règle) enregistrer ses autres réglages. Les deux
    # coordonnées vont ensemble.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    preparation_days: int | None = Field(
        default=None, ge=0, le=14, description="Délai de préparation habituel, en jours"
    )


    @model_validator(mode="after")
    def _position_is_complete(self) -> "VendorOwnerUpdate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("La latitude et la longitude doivent être renseignées ensemble.")
        return self


class VendorAdminUpdate(BaseModel):
    status: VendorStatus | None = None
    commission_rate: float | None = Field(default=None, ge=0, le=100)


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    shop_name: str
    status: VendorStatus
    zone: str | None
    latitude: float | None
    longitude: float | None
    commission_rate: float
    preparation_days: int
    # Attachés en lecture depuis User (voir app/vendors/repository.py) —
    # défauts sûrs pour tout appelant qui ne ferait pas la jointure.
    owner_phone: str | None = None
    owner_email: str | None = None
    owner_full_name: str | None = None


class VendorPublicRead(BaseModel):
    """Vue publique (/vendors, sans authentification) : ce qu'un visiteur
    peut voir d'une boutique. Jamais le compte du propriétaire (téléphone,
    email, nom) ni la commission — voir VendorRead pour le vendeur lui-même
    et l'admin."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_name: str
    zone: str | None
    latitude: float | None
    longitude: float | None
    preparation_days: int


class LowStockProduct(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    stock: int


class VendorDashboard(BaseModel):
    total_orders: int
    active_orders: int
    delivered_orders: int
    cancelled_orders: int
    revenue_delivered: int
    commission_due: int
    net_revenue: int
    active_product_count: int
    low_stock_products: list[LowStockProduct]
    out_of_stock_products: list[LowStockProduct]


class DailyOrderCount(BaseModel):
    day: date
    order_count: int
