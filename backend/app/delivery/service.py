"""Delivery fee computation and admin management of the fee grid."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.geo import haversine_km
from app.core.exceptions import ConflictError, NotFoundError
from app.delivery import repository
from app.delivery.models import DeliveryFeeTier
from app.delivery.schemas import DeliveryFeeTierCreate, DeliveryFeeTierUpdate


# Repli quand il n'existe aucun palier du tout — seul cas où compute_transit_days
# ne peut rien lire de la grille admin. Coïncide avec l'ancienne heuristique de
# zones différentes, avant l'ajout de transit_days par palier.
_DEFAULT_TRANSIT_DAYS_WITHOUT_TIERS = 1


def _bounded_and_catch_all(
    tiers: Sequence[DeliveryFeeTier],
) -> tuple[list[DeliveryFeeTier], DeliveryFeeTier | None]:
    bounded = sorted((t for t in tiers if t.max_km is not None), key=lambda t: t.max_km)
    catch_all = next((t for t in tiers if t.max_km is None), None)
    return bounded, catch_all


def _distance_km(
    origin: tuple[float | None, float | None], destination: tuple[float | None, float | None]
) -> float | None:
    (o_lat, o_lng), (d_lat, d_lng) = origin, destination
    if None in (o_lat, o_lng, d_lat, d_lng):
        return None
    return haversine_km(o_lat, o_lng, d_lat, d_lng)


def _matching_bounded_tier(bounded: Sequence[DeliveryFeeTier], distance_km: float) -> DeliveryFeeTier | None:
    for tier in bounded:
        if distance_km <= tier.max_km:
            return tier
    return None


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
    bounded, catch_all = _bounded_and_catch_all(tiers)
    fallback = catch_all.fee if catch_all is not None else max(t.fee for t in tiers)

    distance = _distance_km(origin, destination)
    if distance is None:
        return fallback
    matched = _matching_bounded_tier(bounded, distance)
    return matched.fee if matched is not None else fallback


def compute_transit_days(
    tiers: Sequence[DeliveryFeeTier],
    origin: tuple[float | None, float | None],
    destination: tuple[float | None, float | None],
) -> int:
    """Extra transit days (on top of the vendor's own preparation time, see
    app/common/delivery_estimate.py) for a parcel, read from the same
    admin-managed distance grid as compute_fee — so the delivery window
    shown to the buyer is grounded in the same real geography as the fee,
    rather than the free-text zone comparison this replaced.

    Same fallback rules as compute_fee: the catch-all tier (or, missing
    one, the slowest bounded tier) when a position is unknown or the
    distance exceeds every bounded tier. Without any tier at all there is no
    grid to read from, so _DEFAULT_TRANSIT_DAYS_WITHOUT_TIERS applies.
    """
    if not tiers:
        return _DEFAULT_TRANSIT_DAYS_WITHOUT_TIERS
    bounded, catch_all = _bounded_and_catch_all(tiers)
    fallback = catch_all.transit_days if catch_all is not None else max(t.transit_days for t in tiers)

    distance = _distance_km(origin, destination)
    if distance is None:
        return fallback
    matched = _matching_bounded_tier(bounded, distance)
    return matched.transit_days if matched is not None else fallback


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
    tier = await repository.create(
        db, max_km=data.max_km, fee=data.fee, label=label, transit_days=data.transit_days
    )
    await db.commit()
    return tier


async def update_tier(db: AsyncSession, tier_id: uuid.UUID, data: DeliveryFeeTierUpdate) -> DeliveryFeeTier:
    tier = await repository.get_by_id(db, tier_id)
    if tier is None:
        raise NotFoundError("Palier introuvable.")
    fields = data.model_dump(exclude_unset=True)
    if "fee" in fields and fields["fee"] is None:
        raise ConflictError("Le tarif du palier est obligatoire.")
    if "transit_days" in fields and fields["transit_days"] is None:
        raise ConflictError("Le délai de trajet du palier est obligatoire.")
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
