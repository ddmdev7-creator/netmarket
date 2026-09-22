"""Database access for delivery fee tiers."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryFeeTier


async def list_all(db: AsyncSession) -> list[DeliveryFeeTier]:
    # Bornés par distance croissante, le palier "au-delà" (NULL) en dernier.
    stmt = select(DeliveryFeeTier).order_by(DeliveryFeeTier.max_km.asc().nulls_last())
    return list((await db.execute(stmt)).scalars().all())


async def get_by_id(db: AsyncSession, tier_id: uuid.UUID) -> DeliveryFeeTier | None:
    return await db.get(DeliveryFeeTier, tier_id)


async def get_by_max_km(db: AsyncSession, max_km: float | None) -> DeliveryFeeTier | None:
    condition = DeliveryFeeTier.max_km.is_(None) if max_km is None else DeliveryFeeTier.max_km == max_km
    return (await db.execute(select(DeliveryFeeTier).where(condition))).scalar_one_or_none()


async def create(db: AsyncSession, *, max_km: float | None, fee: int, label: str | None) -> DeliveryFeeTier:
    tier = DeliveryFeeTier(max_km=max_km, fee=fee, label=label)
    db.add(tier)
    await db.flush()
    return tier


async def delete(db: AsyncSession, tier: DeliveryFeeTier) -> None:
    await db.delete(tier)
    await db.flush()
