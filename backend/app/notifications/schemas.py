"""Pydantic schemas for the in-app notification feed."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.notifications.models import NotificationType


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    order_id: uuid.UUID | None
    sub_order_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationRead]
    unread_count: int
