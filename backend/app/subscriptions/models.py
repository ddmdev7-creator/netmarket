"""Vendor subscription ORM models.

No real online payment gateway exists yet (see app/payments/provider.py —
only cash on delivery is wired up, NimbaPay pending merchant docs), so a
subscription request starts PENDING and is confirmed manually by an admin
once the vendor has paid off-platform (mobile money), the same stopgap the
rest of the app already lives with for payments.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class SubscriptionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SubscriptionPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "subscription_plans"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_gnf: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # Permet de retirer un plan de la vente sans casser l'historique des
    # abonnements qui le référencent déjà.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class VendorSubscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vendor_subscriptions"

    # Plusieurs lignes possibles par vendeur (historique) — celle qui compte
    # est la plus récente, voir subscriptions/repository.py.
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status", values_callable=lambda enum: [e.value for e in enum]),
        default=SubscriptionStatus.PENDING,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Référence transaction chez le prestataire externe une fois NimbaPay
    # branché — même rôle que Payment.provider_reference, toujours None
    # aujourd'hui (confirmation manuelle par un admin).
    payment_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)

    plan: Mapped["SubscriptionPlan"] = relationship()
