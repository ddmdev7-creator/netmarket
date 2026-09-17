"""Pydantic schemas for vendor onboarding, profile and admin validation."""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.vendors.models import VendorStatus


class VendorRegister(BaseModel):
    shop_name: str = Field(min_length=2, max_length=150)
    zone: str | None = Field(default=None, max_length=150)
    # Email is optional at buyer registration but required to become a
    # vendor — see app/vendors/service.py::register_vendor, which uses it to
    # send the verification code gating access to the vendor dashboard.
    email: EmailStr
    # Position de la boutique, optionnelle dès la création — voir
    # app/orders/service.py::start_dispatch, qui en a besoin pour trier les
    # livreurs candidats par distance. Peut aussi être renseignée/mise à
    # jour plus tard via VendorOwnerUpdate.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class VendorOwnerUpdate(BaseModel):
    shop_name: str | None = Field(default=None, min_length=2, max_length=150)
    zone: str | None = Field(default=None, max_length=150)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    preparation_days: int | None = Field(
        default=None, ge=0, le=14, description="Délai de préparation habituel, en jours"
    )


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
