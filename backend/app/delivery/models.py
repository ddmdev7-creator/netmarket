"""DeliveryFeeTier ORM model: one row of the admin-editable distance grid
that prices a sub-order's delivery (see service.compute_fee).

A tier covers "up to max_km"; the single tier with max_km NULL is the
catch-all ("au-delà", and also the fallback when a distance can't be
computed because a GPS position is missing).
"""

from sqlalchemy import CheckConstraint, Float, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class DeliveryFeeTier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "delivery_fee_tiers"
    __table_args__ = (
        CheckConstraint("fee >= 0", name="ck_delivery_fee_tiers_fee_non_negative"),
        CheckConstraint("max_km IS NULL OR max_km > 0", name="ck_delivery_fee_tiers_max_km_positive"),
        # NULL n'est jamais égal à NULL pour un unique classique : sans cet
        # index partiel, on pourrait créer plusieurs paliers "au-delà".
        Index("uq_delivery_fee_tiers_max_km", "max_km", unique=True),
        Index(
            "uq_delivery_fee_tiers_catch_all",
            "max_km",
            unique=True,
            postgresql_where="max_km IS NULL",
        ),
    )

    max_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    # GNF, entier comme tous les montants de l'app.
    fee: Mapped[int] = mapped_column(Integer, nullable=False)
