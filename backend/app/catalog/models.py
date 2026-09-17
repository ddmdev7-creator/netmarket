"""Category and Product ORM models."""

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Category(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )


class ProductStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Franc guinéen : montants entiers, sans décimales.
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    images: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status", values_callable=lambda enum: [e.value for e in enum]),
        default=ProductStatus.ACTIVE,
        nullable=False,
    )

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductVariant.created_at"
    )


class ProductVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Déclinaison d'un produit (couleur, taille, etc.) — entièrement
    optionnelle : un produit sans variante fonctionne exactement comme avant
    (stock/prix au niveau produit). Dès qu'un produit a au moins une
    variante, Product.stock devient une somme dénormalisée du stock de ses
    variantes (voir app/catalog/service.py::_sync_product_stock_from_variants)
    — choix délibéré pour que les filtres/tris/tableaux de bord existants
    (in_stock, stock_level...) continuent de fonctionner sans changement.
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_variants_price_non_negative"),
        CheckConstraint("stock >= 0", name="ck_product_variants_stock_non_negative"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Surcharge absolue du prix du produit ; None = reprend Product.price.
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # None = reprend Product.images ; sinon des photos propres à cette variante.
    images: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="variants")
    attributes: Mapped[list["ProductVariantAttribute"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan", order_by="ProductVariantAttribute.created_at"
    )

    def label(self) -> str:
        """Ex: "Couleur : Rouge, Taille : M" — utilisé pour figer OrderItem.variant_label
        au checkout (voir app/orders/service.py), même logique que product_name/unit_price
        déjà gelés sur OrderItem."""
        return ", ".join(f"{a.name} : {a.value}" for a in self.attributes)


class ProductVariantAttribute(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Paire attribut/valeur libre (ex: "Couleur"/"Rouge") rattachée à une
    variante — pas de taxonomie partagée entre vendeurs (texte libre), voir
    la conception dans le plan produit."""

    __tablename__ = "product_variant_attributes"
    __table_args__ = (UniqueConstraint("variant_id", "name", name="uq_product_variant_attributes_variant_name"),)

    variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)

    variant: Mapped["ProductVariant"] = relationship(back_populates="attributes")
