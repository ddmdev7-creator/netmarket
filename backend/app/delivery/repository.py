"""Database access for delivery fee tiers."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryFeeTier, TierKind


async def list_all(db: AsyncSession, kind: TierKind | None = TierKind.HOME) -> list[DeliveryFeeTier]:
    """Paliers d'une grille (domicile par défaut — celle qui sert aussi aux
    délais affichés au catalogue), ou de toutes avec kind=None (admin)."""
    # Bornés par distance croissante, le palier "au-delà" (NULL) en dernier.
    stmt = select(DeliveryFeeTier).order_by(DeliveryFeeTier.kind, DeliveryFeeTier.max_km.asc().nulls_last())
    if kind is not None:
        stmt = stmt.where(DeliveryFeeTier.kind == kind)
    return list((await db.execute(stmt)).scalars().all())


async def get_by_id(db: AsyncSession, tier_id: uuid.UUID) -> DeliveryFeeTier | None:
    return await db.get(DeliveryFeeTier, tier_id)


async def get_by_max_km(db: AsyncSession, kind: str, max_km: float | None) -> DeliveryFeeTier | None:
    condition = DeliveryFeeTier.max_km.is_(None) if max_km is None else DeliveryFeeTier.max_km == max_km
    stmt = select(DeliveryFeeTier).where(DeliveryFeeTier.kind == kind, condition)
    return (await db.execute(stmt)).scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    kind: str = TierKind.HOME,
    max_km: float | None,
    fee: int,
    label: str | None,
    transit_days: int,
    is_default: bool = False,
) -> DeliveryFeeTier:
    tier = DeliveryFeeTier(
        kind=kind, max_km=max_km, fee=fee, label=label, transit_days=transit_days, is_default=is_default
    )
    db.add(tier)
    await db.flush()
    return tier


async def delete(db: AsyncSession, tier: DeliveryFeeTier) -> None:
    await db.delete(tier)
    await db.flush()
