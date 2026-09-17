"""CartItem ORM model: one row per (user, product), quantity aggregated on add."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class CartItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cart_items"
    __table_args__ = (
        # Note : Postgres traite chaque NULL comme distinct, donc cette
        # contrainte n'empêche pas à elle seule deux lignes sans variante
        # pour le même produit — comme aujourd'hui, la vraie protection
        # contre les doublons reste applicative (voir
        # cart/repository.py::get_item_by_product_and_variant).
        UniqueConstraint("user_id", "product_id", "variant_id", name="uq_cart_items_user_product_variant"),
        CheckConstraint("quantity >= 1", name="ck_cart_items_quantity_positive"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    # Donnée transitoire (contrairement à OrderItem.variant_id) : si la
    # variante est supprimée, la ligne panier disparaît avec elle plutôt que
    # de retomber silencieusement sur le produit de base (mauvais stock/prix).
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
