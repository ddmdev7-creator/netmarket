"""PickupPoint ORM model: an admin-curated physical location where packages
are received, stored and handed off to buyers (own depot or vetted partner).

Not linked by FK to Address — when a buyer picks one at address creation, its
name/zone is frozen as plain text onto their Address (same "freeze at
creation" pattern as shop_name/product_name on orders), so renaming or
deactivating a point later never silently changes a buyer's saved address.
"""

import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class PickupPoint(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pickup_points"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Zone/quartier + repère textuel, même logique que Address.zone.
    zone: Mapped[str] = mapped_column(String(300), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Désactivé plutôt que supprimé pour ne pas casser les adresses qui l'ont
    # déjà figé en texte — juste retiré de la liste proposée aux acheteurs.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Optionnel : renseigné quand ce point EST la boutique d'un vendeur
    # (au lieu d'un local dédié uniquement au retrait) — le vendeur garde son
    # compte habituel, aucun rôle supplémentaire à gérer. ON DELETE SET NULL :
    # si le vendeur est supprimé, le point reste utilisable comme un point
    # "indépendant" plutôt que de disparaître avec lui.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True
    )
    # Texte libre (ex. « Lun–Sam 8h–20h »), repris de la candidature du
    # gestionnaire (app/pickup_point_applications) ou saisi par l'admin.
    opening_hours: Mapped[str | None] = mapped_column(String(300), nullable=True)


class PickupPointReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A buyer's rating + comment on a pickup point they actually used for a
    delivered order — same "verified use" gate as app/reviews/models.py::Review,
    see app/orders/repository.py::has_used_pickup_point_for_user."""

    __tablename__ = "pickup_point_reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_pickup_point_reviews_rating_range"),
        UniqueConstraint("pickup_point_id", "user_id", name="uq_pickup_point_reviews_point_user"),
    )

    pickup_point_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pickup_points.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
