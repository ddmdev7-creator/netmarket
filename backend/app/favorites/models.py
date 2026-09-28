"""Produits favoris d'un acheteur."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Favorite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Prix affiché quand le produit a été ajouté — base du badge « prix en baisse ».
    price_at_add: Mapped[int] = mapped_column(Integer, nullable=False)
    # Dernier prix pour lequel l'acheteur a été alerté : une nouvelle alerte
    # « prix en baisse » ne part que sous ce prix (pas à chaque modification).
    alerted_price: Mapped[int] = mapped_column(Integer, nullable=False)
    back_in_stock_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
