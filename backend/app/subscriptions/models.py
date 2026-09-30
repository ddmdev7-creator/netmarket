"""Vendor subscription ORM models.

Subscriptions aren't wired to the Djomy provider yet (see
app/payments/provider.py, used by orders/ checkout) — a subscription
request starts PENDING and is confirmed manually by an admin once the
vendor has paid off-platform (mobile money), a stopgap until this module
also goes through DjomyProvider.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
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
    # Formule « Gratuit » : jamais souscrite, elle porte les quotas de base de
    # tout vendeur sans abonnement en cours (une seule ligne, voir quotas.py).
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # --- Quotas (None = illimité) — voir app/subscriptions/quotas.py ---
    max_products: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_images_per_product: Mapped[int] = mapped_column(Integer, default=4, server_default="4", nullable=False)
    ai_enhancements_per_month: Mapped[int | None] = mapped_column(Integer, default=0, server_default="0", nullable=True)
    # Mises en avant (phase 2) : affiché, pas encore consommé.
    featured_per_month: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # Points de commission retirés au taux du vendeur (10 % − 2 = 8 %).
    commission_discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0, server_default="0", nullable=False)


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
    # Référence transaction chez le prestataire externe une fois Djomy
    # branché ici aussi — même rôle que Payment.provider_reference, toujours
    # None aujourd'hui (confirmation manuelle par un admin).
    payment_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Essai gratuit offert (admin ou automatique à l'approbation de la boutique).
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Dernier rappel de fin envoyé (nombre de jours restants) : évite les doublons.
    last_reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Fin de la période de grâce traitée (produits en trop masqués).
    grace_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped["SubscriptionPlan"] = relationship()


class UsageKind(StrEnum):
    AI_ENHANCEMENT = "ai_enhancement"
    FEATURED = "featured"


class SubscriptionUsage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Une ligne par consommation d'un quota mensuel (amélioration IA…) —
    compter les lignes du mois civil suffit, pas de compteur à remettre à zéro."""

    __tablename__ = "subscription_usage"
    __table_args__ = (Index("ix_subscription_usage_vendor_kind_created", "vendor_id", "kind", "created_at"),)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)


class SubscriptionSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Réglages des abonnements — une seule ligne (voir repository.get_settings)."""

    __tablename__ = "subscription_settings"

    # Essai offert automatiquement à chaque boutique approuvée.
    auto_trial_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    auto_trial_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True
    )
    auto_trial_days: Mapped[int] = mapped_column(Integer, default=14, server_default="14", nullable=False)
    # Jours après la fin avant de masquer les produits au-delà du quota gratuit.
    grace_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7", nullable=False)
