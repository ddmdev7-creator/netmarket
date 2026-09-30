"""DeliveryFeeTier ORM model: one row of the admin-editable distance grid
that prices a sub-order's delivery (see service.compute_fee).

A tier covers "up to max_km"; the single tier with max_km NULL is the
catch-all ("au-delà", and also the fallback when a distance can't be
computed because a GPS position is missing).

Two grids live in this table (`kind`): home delivery, and an optional
dedicated pickup-point grid — see service.grid_for for how the pickup price
is chosen (dedicated grid, or a percentage of the home grid).
"""

from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class TierKind(StrEnum):
    HOME = "home"
    PICKUP = "pickup"


class PickupPricingMode(StrEnum):
    # Tarif domicile × PaymentSettings.pickup_fee_percent.
    PERCENT = "percent"
    # Grille dédiée (paliers kind=pickup) ; vide → repli sur PERCENT.
    GRID = "grid"


class DeliveryFeeTier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "delivery_fee_tiers"
    __table_args__ = (
        CheckConstraint("fee >= 0", name="ck_delivery_fee_tiers_fee_non_negative"),
        CheckConstraint("max_km IS NULL OR max_km > 0", name="ck_delivery_fee_tiers_max_km_positive"),
        CheckConstraint("transit_days >= 0", name="ck_delivery_fee_tiers_transit_days_non_negative"),
        # NULL n'est jamais égal à NULL pour un unique classique : sans cet
        # index partiel, on pourrait créer plusieurs paliers "au-delà".
        Index("uq_delivery_fee_tiers_max_km", "kind", "max_km", unique=True),
        Index(
            "uq_delivery_fee_tiers_catch_all",
            "kind",
            unique=True,
            postgresql_where="max_km IS NULL",
        ),
        Index("uq_delivery_fee_tiers_default", "kind", unique=True, postgresql_where="is_default"),
    )

    # Grille à laquelle appartient le palier (TierKind) — chaque grille a ses
    # propres unicités (distance, « au-delà », « par défaut »).
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=TierKind.HOME, server_default=TierKind.HOME.value)

    max_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Libellé libre à l'usage de l'admin (ex. "Grand Conakry — Coyah, Dubréka") :
    # purement informatif, le calcul ne repose que sur max_km.
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # GNF, entier comme tous les montants de l'app.
    fee: Mapped[int] = mapped_column(Integer, nullable=False)
    # Jours de trajet supplémentaires pour ce palier, au-delà du délai de
    # préparation du vendeur (Vendor.preparation_days) — voir
    # app/delivery/service.py::compute_transit_days et
    # app/common/delivery_estimate.py. Même grille que le tarif plutôt qu'une
    # heuristique de zone séparée : la durée annoncée à l'acheteur repose
    # ainsi sur la même distance réelle que le prix qu'il voit.
    transit_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Palier « par défaut » : appliqué quand la distance ne peut pas être
    # calculée (l'acheteur n'a pas pu donner sa position GPS). Au plus un
    # palier l'est ; sans palier par défaut, c'est le palier « au-delà ».
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
