"""Delivery fee computation and admin management of the fee grid."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.geo import haversine_km
from app.core.exceptions import ConflictError, NotFoundError
from app.delivery import repository
from app.delivery.models import DeliveryFeeTier
from app.delivery.schemas import DeliveryFeeTierCreate, DeliveryFeeTierUpdate


def compute_fee(
    tiers: Sequence[DeliveryFeeTier],
    origin: tuple[float | None, float | None],
    destination: tuple[float | None, float | None],
) -> int:
    """Fee for one parcel from origin (vendor) to destination (buyer address
    or pickup point), from the distance grid.

    Falls back to the catch-all tier (max_km NULL) — or, without one, the
    dearest bounded tier — when a position is missing or the distance
    exceeds every bounded tier: overcharging slightly is preferable to a
    free delivery nobody is paid for. No tiers at all means delivery is free.
    """
    if not tiers:
        return 0
    bounded = sorted((t for t in tiers if t.max_km is not None), key=lambda t: t.max_km)
    catch_all = next((t for t in tiers if t.max_km is None), None)
    fallback = catch_all.fee if catch_all is not None else max(t.fee for t in tiers)

    (o_lat, o_lng), (d_lat, d_lng) = origin, destination
    if None in (o_lat, o_lng, d_lat, d_lng):
        return fallback
    distance = haversine_km(o_lat, o_lng, d_lat, d_lng)
    for tier in bounded:
        if distance <= tier.max_km:
            return tier.fee
    return fallback


async def list_tiers(db: AsyncSession) -> list[DeliveryFeeTier]:
    return await repository.list_all(db)


async def _ensure_max_km_free(db: AsyncSession, max_km: float | None, *, ignore_id: uuid.UUID | None = None) -> None:
    existing = await repository.get_by_max_km(db, max_km)
    if existing is not None and existing.id != ignore_id:
        raise ConflictError(
            "Un palier « au-delà » existe déjà." if max_km is None else f"Un palier jusqu'à {max_km:g} km existe déjà."
        )


async def create_tier(db: AsyncSession, data: DeliveryFeeTierCreate) -> DeliveryFeeTier:
    await _ensure_max_km_free(db, data.max_km)
    label = (data.label or "").strip() or None
    tier = await repository.create(db, max_km=data.max_km, fee=data.fee, label=label)
    await db.commit()
    return tier


async def update_tier(db: AsyncSession, tier_id: uuid.UUID, data: DeliveryFeeTierUpdate) -> DeliveryFeeTier:
    tier = await repository.get_by_id(db, tier_id)
    if tier is None:
        raise NotFoundError("Palier introuvable.")
    fields = data.model_dump(exclude_unset=True)
    if "fee" in fields and fields["fee"] is None:
        raise ConflictError("Le tarif du palier est obligatoire.")
    if "max_km" in fields:
        await _ensure_max_km_free(db, fields["max_km"], ignore_id=tier.id)
    if "label" in fields:
        fields["label"] = (fields["label"] or "").strip() or None
    for field, value in fields.items():
        setattr(tier, field, value)
    await db.commit()
    return tier


async def delete_tier(db: AsyncSession, tier_id: uuid.UUID) -> None:
    tier = await repository.get_by_id(db, tier_id)
    if tier is None:
        raise NotFoundError("Palier introuvable.")
    await repository.delete(db, tier)
    await db.commit()
