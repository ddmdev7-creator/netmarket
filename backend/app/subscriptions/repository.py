"""Database access for subscription plans and vendor subscriptions."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.subscriptions.models import SubscriptionPlan, SubscriptionStatus, VendorSubscription


async def list_active_plans(db: AsyncSession) -> list[SubscriptionPlan]:
    """Formules en vente (hors Gratuit), de la moins chère à la plus chère."""
    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active.is_(True), SubscriptionPlan.is_free.is_(False))
        .order_by(SubscriptionPlan.sort_order, SubscriptionPlan.price_gnf)
    )
    return list(result.scalars().all())


async def list_all_plans(db: AsyncSession) -> list[SubscriptionPlan]:
    result = await db.execute(
        select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order, SubscriptionPlan.price_gnf)
    )
    return list(result.scalars().all())


async def get_plan_by_id(db: AsyncSession, plan_id: uuid.UUID) -> SubscriptionPlan | None:
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    plan_id: uuid.UUID,
    status: SubscriptionStatus,
    is_trial: bool = False,
    started_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> VendorSubscription:
    subscription = VendorSubscription(
        vendor_id=vendor_id,
        plan_id=plan_id,
        status=status,
        is_trial=is_trial,
        started_at=started_at,
        expires_at=expires_at,
    )
    db.add(subscription)
    await db.flush()
    return subscription


async def get_by_id(db: AsyncSession, subscription_id: uuid.UUID) -> VendorSubscription | None:
    result = await db.execute(
        select(VendorSubscription)
        .where(VendorSubscription.id == subscription_id)
        .options(selectinload(VendorSubscription.plan))
    )
    return result.scalar_one_or_none()


async def list_for_vendor(db: AsyncSession, vendor_id: uuid.UUID, limit: int = 30) -> list[VendorSubscription]:
    result = await db.execute(
        select(VendorSubscription)
        .where(VendorSubscription.vendor_id == vendor_id)
        .options(selectinload(VendorSubscription.plan))
        .order_by(VendorSubscription.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_latest_for_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> VendorSubscription | None:
    rows = await list_for_vendor(db, vendor_id, limit=1)
    return rows[0] if rows else None


async def get_pending(db: AsyncSession, vendor_id: uuid.UUID) -> VendorSubscription | None:
    result = await db.execute(
        select(VendorSubscription)
        .where(VendorSubscription.vendor_id == vendor_id, VendorSubscription.status == SubscriptionStatus.PENDING)
        .options(selectinload(VendorSubscription.plan))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def latest_active_end(db: AsyncSession, vendor_id: uuid.UUID, now: datetime) -> datetime | None:
    """Fin de la dernière période active ou déjà programmée — un
    renouvellement démarre là (ou maintenant s'il n'y en a pas)."""
    result = await db.execute(
        select(VendorSubscription.expires_at)
        .where(
            VendorSubscription.vendor_id == vendor_id,
            VendorSubscription.status == SubscriptionStatus.ACTIVE,
            VendorSubscription.expires_at > now,
        )
        .order_by(VendorSubscription.expires_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_scheduled(db: AsyncSession, vendor_id: uuid.UUID, now: datetime) -> VendorSubscription | None:
    result = await db.execute(
        select(VendorSubscription)
        .where(
            VendorSubscription.vendor_id == vendor_id,
            VendorSubscription.status == SubscriptionStatus.ACTIVE,
            VendorSubscription.started_at > now,
        )
        .options(selectinload(VendorSubscription.plan))
        .order_by(VendorSubscription.started_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def trial_plan_ids(db: AsyncSession, vendor_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(VendorSubscription.plan_id)
        .where(VendorSubscription.vendor_id == vendor_id, VendorSubscription.is_trial.is_(True))
        .distinct()
    )
    return list(result.scalars().all())


async def list_by_status(db: AsyncSession, status: SubscriptionStatus | None) -> list[VendorSubscription]:
    stmt = select(VendorSubscription).options(selectinload(VendorSubscription.plan))
    if status is not None:
        stmt = stmt.where(VendorSubscription.status == status)
    result = await db.execute(stmt.order_by(VendorSubscription.created_at.desc()))
    return list(result.scalars().all())
