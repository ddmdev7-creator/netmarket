"""Pydantic schemas for subscription plans and vendor subscriptions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.subscriptions.models import SubscriptionStatus


class SubscriptionPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    name: str
    price_gnf: int
    duration_days: int
    is_free: bool = False
    is_active: bool = True
    description: str | None = None
    sort_order: int = 0
    # Quotas — None = illimité.
    max_products: int | None = None
    max_images_per_product: int = 4
    ai_enhancements_per_month: int | None = 0
    featured_per_month: int = 0
    commission_discount: float = 0


class SubscriptionPlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    price_gnf: int = Field(ge=0, le=100_000_000)
    duration_days: int = Field(ge=1, le=3660)
    is_active: bool = True
    description: str | None = Field(default=None, max_length=300)
    sort_order: int = Field(default=0, ge=0, le=100)
    max_products: int | None = Field(default=None, ge=0, le=100_000)
    max_images_per_product: int = Field(default=4, ge=1, le=50)
    ai_enhancements_per_month: int | None = Field(default=0, ge=0, le=100_000)
    featured_per_month: int = Field(default=0, ge=0, le=1000)
    commission_discount: float = Field(default=0, ge=0, le=100)


class SubscriptionPlanUpdate(BaseModel):
    """PATCH : les champs quota acceptent None (= illimité), d'où exclude_unset côté service."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    price_gnf: int | None = Field(default=None, ge=0, le=100_000_000)
    duration_days: int | None = Field(default=None, ge=1, le=3660)
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=300)
    sort_order: int | None = Field(default=None, ge=0, le=100)
    max_products: int | None = Field(default=None, ge=0, le=100_000)
    max_images_per_product: int | None = Field(default=None, ge=1, le=50)
    ai_enhancements_per_month: int | None = Field(default=None, ge=0, le=100_000)
    featured_per_month: int | None = Field(default=None, ge=0, le=1000)
    commission_discount: float | None = Field(default=None, ge=0, le=100)


class SubscribeRequest(BaseModel):
    plan_id: uuid.UUID


class VendorSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    status: SubscriptionStatus
    started_at: datetime | None
    expires_at: datetime | None
    is_trial: bool = False
    created_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    plan: SubscriptionPlanRead


class QuotaUsage(BaseModel):
    used: int
    # None = illimité.
    limit: int | None


class SubscriptionOverview(BaseModel):
    """Tout ce que la page abonnement affiche, vendeur comme admin."""

    # Formule qui s'applique maintenant (en cours, sinon Gratuit).
    plan: SubscriptionPlanRead
    current: VendorSubscriptionRead | None
    # Renouvellement payé d'avance, qui démarre à la fin de `current`.
    scheduled: VendorSubscriptionRead | None
    pending: VendorSubscriptionRead | None
    # Fin de la période de grâce après expiration (produits en trop masqués ensuite).
    grace_until: datetime | None
    products: QuotaUsage
    ai_enhancements: QuotaUsage
    ai_resets_at: datetime
    max_images_per_product: int
    featured_per_month: int
    base_commission_rate: float
    effective_commission_rate: float
    history: list[VendorSubscriptionRead]
    trial_used_plan_ids: list[uuid.UUID]
    plans: list[SubscriptionPlanRead]


class AdminSubscriptionRead(VendorSubscriptionRead):
    """Vue admin : qui s'est abonné, depuis quand, et la référence de paiement."""

    payment_reference: str | None = None
    shop_name: str = ""
    vendor_zone: str | None = None
    vendor_status: str | None = None
    owner_user_id: uuid.UUID | None = None
    owner_full_name: str | None = None
    owner_phone: str | None = None
    owner_email: str | None = None
    products_used: int = 0


class AdminCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class AdminExtendRequest(BaseModel):
    days: int = Field(ge=1, le=3660)


class AdminChangePlanRequest(BaseModel):
    plan_id: uuid.UUID


class AdminTrialRequest(BaseModel):
    vendor_id: uuid.UUID
    plan_id: uuid.UUID
    days: int = Field(default=14, ge=1, le=90)


class SubscriptionSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    auto_trial_enabled: bool
    auto_trial_plan_id: uuid.UUID | None
    auto_trial_days: int
    grace_days: int


class SubscriptionSettingsUpdate(BaseModel):
    auto_trial_enabled: bool | None = None
    auto_trial_plan_id: uuid.UUID | None = None
    auto_trial_days: int | None = Field(default=None, ge=1, le=90)
    grace_days: int | None = Field(default=None, ge=0, le=60)
