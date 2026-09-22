"""Pydantic schemas for the payments module's admin-editable settings."""

from pydantic import BaseModel, ConfigDict, Field


class PaymentSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    refund_delay_hours: int


class PaymentSettingsUpdate(BaseModel):
    refund_delay_hours: int = Field(ge=0, le=24 * 30)
