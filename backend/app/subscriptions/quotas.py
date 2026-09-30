"""Droits d'un vendeur selon sa formule : quotas et commission réduite.

La formule effective est celle de l'abonnement en cours (payé ou essai),
sinon la formule « Gratuit » (SubscriptionPlan.is_free). Sans formule
Gratuit en base (tests, base neuve avant migration), aucune limite ne
s'applique sauf l'IA, fermée — même comportement qu'avant les quotas.

Dépassement : ForbiddenError (403) avec un message qui dit quoi faire.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenError
from app.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionSettings,
    SubscriptionStatus,
    SubscriptionUsage,
    UsageKind,
    VendorSubscription,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(now: datetime) -> datetime:
    start = month_start(now)
    return (start + timedelta(days=32)).replace(day=1)


# Formule de repli quand aucune formule Gratuit n'existe en base.
def _unlimited_free_plan() -> SubscriptionPlan:
    return SubscriptionPlan(
        name="Gratuit",
        price_gnf=0,
        duration_days=0,
        is_active=True,
        is_free=True,
        sort_order=0,
        max_products=None,
        max_images_per_product=50,
        ai_enhancements_per_month=0,
        featured_per_month=0,
        commission_discount=0,
    )


async def get_free_plan(db: AsyncSession) -> SubscriptionPlan:
    plan = (
        await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_free.is_(True)).limit(1))
    ).scalar_one_or_none()
    return plan or _unlimited_free_plan()


async def get_settings(db: AsyncSession) -> SubscriptionSettings:
    row = (await db.execute(select(SubscriptionSettings).limit(1))).scalar_one_or_none()
    if row is None:
        row = SubscriptionSettings(auto_trial_enabled=False, auto_trial_days=14, grace_days=7)
        db.add(row)
        await db.flush()
    return row


async def current_subscription(
    db: AsyncSession, vendor_id: uuid.UUID, now: datetime | None = None
) -> VendorSubscription | None:
    """Abonnement qui couvre l'instant présent (un renouvellement payé
    d'avance a un started_at futur et n'est pas encore « en cours »)."""
    now = now or now_utc()
    return (
        await db.execute(
            select(VendorSubscription)
            .where(
                VendorSubscription.vendor_id == vendor_id,
                VendorSubscription.status == SubscriptionStatus.ACTIVE,
                VendorSubscription.started_at <= now,
                VendorSubscription.expires_at > now,
            )
            .options(selectinload(VendorSubscription.plan))
            .order_by(VendorSubscription.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


@dataclass
class Entitlements:
    plan: SubscriptionPlan
    subscription: VendorSubscription | None


async def entitlements(db: AsyncSession, vendor_id: uuid.UUID) -> Entitlements:
    subscription = await current_subscription(db, vendor_id)
    if subscription is not None:
        return Entitlements(plan=subscription.plan, subscription=subscription)
    return Entitlements(plan=await get_free_plan(db), subscription=None)


# --- Produits ---------------------------------------------------------------


async def count_active_products(db: AsyncSession, vendor_id: uuid.UUID) -> int:
    from app.catalog.models import Product, ProductStatus

    stmt = select(func.count()).select_from(Product).where(
        Product.vendor_id == vendor_id, Product.status == ProductStatus.ACTIVE
    )
    return (await db.execute(stmt)).scalar_one()


async def ensure_can_add_active_product(db: AsyncSession, vendor_id: uuid.UUID) -> None:
    plan = (await entitlements(db, vendor_id)).plan
    if plan.max_products is None:
        return
    if await count_active_products(db, vendor_id) >= plan.max_products:
        raise ForbiddenError(
            f"Votre formule {plan.name} permet {plan.max_products} produits en vente. "
            "Masquez un produit ou passez à une formule supérieure pour en publier d'autres."
        )


async def ensure_images_allowed(db: AsyncSession, vendor_id: uuid.UUID, images: list[str] | None) -> None:
    if not images:
        return
    plan = (await entitlements(db, vendor_id)).plan
    if len(images) > plan.max_images_per_product:
        raise ForbiddenError(
            f"Votre formule {plan.name} permet {plan.max_images_per_product} photos par produit "
            f"(vous en avez {len(images)}). Retirez-en ou passez à une formule supérieure."
        )


# --- Améliorations IA (quota mensuel) --------------------------------------


async def usage_this_month(db: AsyncSession, vendor_id: uuid.UUID, kind: UsageKind) -> int:
    stmt = select(func.count()).select_from(SubscriptionUsage).where(
        SubscriptionUsage.vendor_id == vendor_id,
        SubscriptionUsage.kind == kind,
        SubscriptionUsage.created_at >= month_start(now_utc()),
    )
    return (await db.execute(stmt)).scalar_one()


async def ensure_ai_available(db: AsyncSession, vendor_id: uuid.UUID, count: int) -> None:
    plan = (await entitlements(db, vendor_id)).plan
    limit = plan.ai_enhancements_per_month
    if limit is None:
        return
    used = await usage_this_month(db, vendor_id, UsageKind.AI_ENHANCEMENT)
    if used + count > limit:
        left = max(0, limit - used)
        if limit == 0:
            raise ForbiddenError(f"L'amélioration IA des photos n'est pas incluse dans la formule {plan.name}.")
        raise ForbiddenError(
            f"Il vous reste {left} amélioration{'s' if left > 1 else ''} IA ce mois-ci "
            f"(formule {plan.name} : {limit} par mois). Passez à une formule supérieure pour en avoir plus."
        )


async def record_usage(db: AsyncSession, vendor_id: uuid.UUID, kind: UsageKind, count: int = 1) -> None:
    db.add_all([SubscriptionUsage(vendor_id=vendor_id, kind=kind) for _ in range(count)])
    await db.commit()


# --- Commission -----------------------------------------------------------------


async def effective_commission_rate(db: AsyncSession, vendor) -> Decimal:
    """Taux du vendeur moins la réduction de sa formule (jamais négatif)."""
    plan = (await entitlements(db, vendor.id)).plan
    rate = Decimal(str(vendor.commission_rate)) - Decimal(str(plan.commission_discount or 0))
    return max(Decimal(0), rate)
