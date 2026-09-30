"""Delivery fee computation and admin management of the fee grid."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.geo import haversine_km
from app.core.exceptions import ConflictError, NotFoundError
from app.delivery import repository
from app.delivery.models import DeliveryFeeTier, PickupPricingMode, TierKind
from app.delivery.schemas import (
    DeliveryFeeTierCreate,
    DeliveryFeeTierUpdate,
    DeliveryPricingSettings,
    DeliveryPricingSettingsUpdate,
)
from app.payments import repository as payments_repository


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


def _unknown_position_tier(
    tiers: Sequence[DeliveryFeeTier], bounded: Sequence[DeliveryFeeTier], catch_all: DeliveryFeeTier | None
) -> DeliveryFeeTier | None:
    """Palier appliqué quand la distance est inconnue (position GPS absente) :
    celui que l'admin a marqué « par défaut », sinon le palier « au-delà »."""
    return next((t for t in tiers if getattr(t, "is_default", False)), None) or catch_all


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

    A missing position uses the tier the admin marked as default
    (is_default). Otherwise — and when the distance exceeds every bounded
    tier — falls back to the catch-all tier (max_km NULL) or, without one, the
    dearest bounded tier: overcharging slightly is preferable to a
    free delivery nobody is paid for. No tiers at all means delivery is free.
    """
    if not tiers:
        return 0
    bounded, catch_all = _bounded_and_catch_all(tiers)
    fallback = catch_all.fee if catch_all is not None else max(t.fee for t in tiers)

    distance = _distance_km(origin, destination)
    if distance is None:
        unknown = _unknown_position_tier(tiers, bounded, catch_all)
        return unknown.fee if unknown is not None else fallback
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
        unknown = _unknown_position_tier(tiers, bounded, catch_all)
        return unknown.transit_days if unknown is not None else fallback
    matched = _matching_bounded_tier(bounded, distance)
    return matched.transit_days if matched is not None else fallback


def _round_fee(amount: float) -> int:
    """Montant en GNF arrondi à la centaine (pas de 10 450 GNF affichés)."""
    return int(round(amount / 100) * 100)


@dataclass
class FeeGrid:
    """Grille qui tarife une livraison : paliers de distance, éventuellement
    ajustés d'un pourcentage (point de retrait en mode PERCENT)."""

    tiers: list[DeliveryFeeTier] = field(default_factory=list)
    percent: int = 100

    def fee(self, origin: tuple[float | None, float | None], destination: tuple[float | None, float | None]) -> int:
        base = compute_fee(self.tiers, origin, destination)
        return base if self.percent == 100 else _round_fee(base * self.percent / 100)

    def transit_days(
        self, origin: tuple[float | None, float | None], destination: tuple[float | None, float | None]
    ) -> int:
        return compute_transit_days(self.tiers, origin, destination)


async def grid_for(db: AsyncSession, *, is_pickup: bool) -> FeeGrid:
    """Domicile : la grille domicile. Point de retrait : la grille dédiée en
    mode GRID si elle a des paliers, sinon la grille domicile × le
    pourcentage réglé par l'admin (100 % = même prix qu'à domicile)."""
    if not is_pickup:
        return FeeGrid(await repository.list_all(db, TierKind.HOME))
    settings_row = await payments_repository.get_settings(db)
    if settings_row.pickup_pricing_mode == PickupPricingMode.GRID:
        pickup_tiers = await repository.list_all(db, TierKind.PICKUP)
        if pickup_tiers:
            return FeeGrid(pickup_tiers)
    return FeeGrid(await repository.list_all(db, TierKind.HOME), percent=settings_row.pickup_fee_percent)


async def get_pricing_settings(db: AsyncSession) -> DeliveryPricingSettings:
    return DeliveryPricingSettings.model_validate(await payments_repository.get_settings(db))


async def update_pricing_settings(db: AsyncSession, data: DeliveryPricingSettingsUpdate) -> DeliveryPricingSettings:
    settings_row = await payments_repository.get_settings(db)
    for name, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(settings_row, name, value)
    await db.commit()
    return DeliveryPricingSettings.model_validate(settings_row)


async def list_tiers(db: AsyncSession) -> list[DeliveryFeeTier]:
    return await repository.list_all(db, kind=None)


async def _ensure_max_km_free(
    db: AsyncSession, kind: str, max_km: float | None, *, ignore_id: uuid.UUID | None = None
) -> None:
    existing = await repository.get_by_max_km(db, kind, max_km)
    if existing is not None and existing.id != ignore_id:
        raise ConflictError(
            "Un palier « au-delà » existe déjà." if max_km is None else f"Un palier jusqu'à {max_km:g} km existe déjà."
        )


async def _clear_default(db: AsyncSession, kind: str) -> None:
    """Un seul palier par défaut par grille : on retire la marque de l'ancien
    avant d'en poser une nouvelle (index unique partiel uq_delivery_fee_tiers_default)."""
    for tier in await repository.list_all(db, TierKind(kind)):
        if tier.is_default:
            tier.is_default = False
    await db.flush()


async def create_tier(db: AsyncSession, data: DeliveryFeeTierCreate) -> DeliveryFeeTier:
    await _ensure_max_km_free(db, data.kind, data.max_km)
    label = (data.label or "").strip() or None
    if data.is_default:
        await _clear_default(db, data.kind)
    tier = await repository.create(
        db,
        kind=data.kind,
        max_km=data.max_km,
        fee=data.fee,
        label=label,
        transit_days=data.transit_days,
        is_default=data.is_default,
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
        await _ensure_max_km_free(db, tier.kind, fields["max_km"], ignore_id=tier.id)
    if "label" in fields:
        fields["label"] = (fields["label"] or "").strip() or None
    if "is_default" in fields:
        if fields["is_default"] is None:
            fields.pop("is_default")
        elif fields["is_default"] and not tier.is_default:
            await _clear_default(db, tier.kind)
    for name, value in fields.items():
        setattr(tier, name, value)
    await db.commit()
    return tier


async def delete_tier(db: AsyncSession, tier_id: uuid.UUID) -> None:
    tier = await repository.get_by_id(db, tier_id)
    if tier is None:
        raise NotFoundError("Palier introuvable.")
    await repository.delete(db, tier)
    await db.commit()
