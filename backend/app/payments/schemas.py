"""Pydantic schemas for the payments module's admin-editable settings."""

from pydantic import BaseModel, ConfigDict, Field


class PaymentSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    refund_delay_hours: int
    cash_on_delivery_enabled: bool


class PaymentSettingsUpdate(BaseModel):
    # Champs absents = inchangés.
    refund_delay_hours: int | None = Field(default=None, ge=0, le=24 * 30)
    cash_on_delivery_enabled: bool | None = None


class PaymentOptionsRead(BaseModel):
    """Moyens de paiement proposés au checkout (public)."""

    cash_on_delivery: bool
    online: bool
    wallet: bool
