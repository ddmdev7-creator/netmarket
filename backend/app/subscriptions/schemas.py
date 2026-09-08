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
