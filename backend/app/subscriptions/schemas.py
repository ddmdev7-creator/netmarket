"""Pydantic schemas for subscription plans and vendor subscriptions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.subscriptions.models import SubscriptionStatus


class SubscriptionPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    price_gnf: int
    duration_days: int


class SubscribeRequest(BaseModel):
    plan_id: uuid.UUID


class VendorSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    status: SubscriptionStatus
    started_at: datetime | None
    expires_at: datetime | None
    plan: SubscriptionPlanRead


class AdminSubscriptionRead(VendorSubscriptionRead):
    """Vue admin : qui s'est abonné, depuis quand, et la référence de paiement."""

    created_at: datetime
    payment_reference: str | None = None
    shop_name: str = ""
    vendor_zone: str | None = None
    vendor_status: str | None = None
    owner_user_id: uuid.UUID | None = None
    owner_full_name: str | None = None
    owner_phone: str | None = None
    owner_email: str | None = None
