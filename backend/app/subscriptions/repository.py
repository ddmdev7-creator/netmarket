"""Database access for subscription plans and vendor subscriptions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.subscriptions.models import SubscriptionPlan, SubscriptionStatus, VendorSubscription


async def list_active_plans(db: AsyncSession) -> list[SubscriptionPlan]:
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.price_gnf)
    )
    return list(result.scalars().all())


async def get_plan_by_id(db: AsyncSession, plan_id: uuid.UUID) -> SubscriptionPlan | None:
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession, *, vendor_id: uuid.UUID, plan_id: uuid.UUID, status: SubscriptionStatus
) -> VendorSubscription:
    subscription = VendorSubscription(vendor_id=vendor_id, plan_id=plan_id, status=status)
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


async def get_latest_for_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> VendorSubscription | None:
    result = await db.execute(
        select(VendorSubscription)
        .where(VendorSubscription.vendor_id == vendor_id)
        .options(selectinload(VendorSubscription.plan))
        .order_by(VendorSubscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def has_pending(db: AsyncSession, vendor_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(VendorSubscription.id).where(
            VendorSubscription.vendor_id == vendor_id, VendorSubscription.status == SubscriptionStatus.PENDING
        )
    )
    return result.scalar_one_or_none() is not None


async def is_premium(db: AsyncSession, vendor_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(VendorSubscription.id).where(
            VendorSubscription.vendor_id == vendor_id,
            VendorSubscription.status == SubscriptionStatus.ACTIVE,
            VendorSubscription.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none() is not None


async def list_by_status(db: AsyncSession, status: SubscriptionStatus | None) -> list[VendorSubscription]:
    stmt = select(VendorSubscription).options(selectinload(VendorSubscription.plan))
    if status is not None:
        stmt = stmt.where(VendorSubscription.status == status)
    result = await db.execute(stmt.order_by(VendorSubscription.created_at.desc()))
    return list(result.scalars().all())
