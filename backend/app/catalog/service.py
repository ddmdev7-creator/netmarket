"""Business logic for categories and products, including vendor ownership checks."""

import uuid
from datetime import date

import nh3
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository
from app.catalog.models import Category, Product, ProductVariant, ProductVariantAttribute
from app.catalog.schemas import (
    CategoryCreate,
    ProductCreate,
    ProductFilters,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.common.delivery_estimate import estimate_delivery_window
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.reviews import repository as reviews_repository
from app.users.models import User, UserRole
from app.vendors import repository as vendor_repository
from app.vendors.models import VendorStatus


def _attach_rating(product: Product, summary: tuple[float, int] | None) -> Product:
    # Transient attributes, same pattern as vendor_shop_name in
    # app/catalog/repository.py: not Product columns, computed on read from
    # the separate reviews table (app/reviews/).
    average, count = summary if summary is not None else (None, 0)
    product.average_rating = average
    product.review_count = count
    return product


def _attach_delivery_estimate(product: Product) -> Product:
    # Generic estimate — the buyer's delivery zone isn't known on the
    # catalog (vs. at checkout, where the real zone gives a firmer estimate
    # frozen onto the SubOrder, see app/orders/service.py::checkout_cart).
    estimate = estimate_delivery_window(
        vendor_zone=product.vendor_zone,
        buyer_zone=None,
        preparation_days=product.vendor_preparation_days,
        from_date=date.today(),
    )
    product.estimated_delivery_min = estimate.min_date
    product.estimated_delivery_max = estimate.max_date
    return product

# Mini éditeur riche côté frontend (ProductForm.vue) : gras, italique,
# listes. Seules ces balises survivent, sans aucun attribut — la
# description est réaffichée telle quelle (v-html) sur la fiche produit à
# tous les acheteurs, donc jamais confiance dans le HTML envoyé par le
# client, même si le frontend ne peut normalement en produire que ce
# sous-ensemble (un appel direct à l'API pourrait envoyer n'importe quoi).
_ALLOWED_DESCRIPTION_TAGS = {"p", "br", "strong", "b", "em", "i", "ul", "ol", "li"}


def _sanitize_description(html: str | None) -> str | None:
    if html is None:
        return None
    cleaned = nh3.clean(html, tags=_ALLOWED_DESCRIPTION_TAGS, attributes={}, strip_comments=True).strip()
    return cleaned or None


# --- Categories (admin only, enforced at router level) ---


async def create_category(db: AsyncSession, data: CategoryCreate) -> Category:
    if data.parent_id is not None and await repository.get_category_by_id(db, data.parent_id) is None:
        raise NotFoundError("Catégorie parente introuvable.")
    category = await repository.create_category(db, name=data.name, parent_id=data.parent_id)
    await db.commit()
    await db.refresh(category)
    return category


async def list_categories(db: AsyncSession) -> list[Category]:
    return await repository.list_categories(db)


async def delete_category(db: AsyncSession, category_id: uuid.UUID) -> None:
    category = await repository.get_category_by_id(db, category_id)
    if category is None:
        raise NotFoundError("Catégorie introuvable.")
    await repository.delete_category(db, category)
    await db.commit()


# --- Products ---


async def _require_own_vendor(db: AsyncSession, user: User) -> uuid.UUID:
    """Resolve the calling vendor's shop and check it is approved. Returns the vendor id."""
    vendor = await vendor_repository.get_by_user_id(db, user.id)
    if vendor is None:
        raise NotFoundError("Profil vendeur introuvable. Veuillez d'abord créer votre boutique.")
    if vendor.status != VendorStatus.APPROVED:
        raise ForbiddenError("Votre boutique doit être validée par un administrateur avant de publier des produits.")
    return vendor.id


async def _check_product_owner(db: AsyncSession, product: Product, user: User) -> None:
    if user.role == UserRole.ADMIN:
        return
    vendor = await vendor_repository.get_by_id(db, product.vendor_id)
    if vendor is None or vendor.user_id != user.id:
        raise ForbiddenError("Vous ne pouvez modifier que les produits de votre propre boutique.")


async def create_product(db: AsyncSession, user: User, data: ProductCreate) -> Product:
    if await repository.get_category_by_id(db, data.category_id) is None:
        raise NotFoundError("Catégorie introuvable.")

    vendor_id = await _require_own_vendor(db, user)
    fields = data.model_dump()
    fields["description"] = _sanitize_description(fields.get("description"))
    product = await repository.create_product(db, vendor_id=vendor_id, **fields)
    await db.commit()
    return await get_product(db, product.id)


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> Product:
    product = await repository.get_product_by_id(db, product_id)
    if product is None:
        raise NotFoundError("Produit introuvable.")
    average, count = await reviews_repository.get_rating_summary(db, product.id)
    _attach_rating(product, (average, count))
    return _attach_delivery_estimate(product)


async def list_products(
    db: AsyncSession, filters: ProductFilters, params: PageParams
) -> tuple[list[Product], int]:
    products, total = await repository.list_products(db, filters=filters, params=params)
    rating_map = await reviews_repository.get_rating_summary_map(db, [p.id for p in products])
    for product in products:
        _attach_rating(product, rating_map.get(product.id))
        _attach_delivery_estimate(product)
    return products, total


async def list_my_products(
    db: AsyncSession, user: User, params: PageParams, filters: ProductFilters
) -> tuple[list[Product], int]:
    vendor = await vendor_repository.get_by_user_id(db, user.id)
    if vendor is None:
        raise NotFoundError("Vous n'avez pas de boutique.")
    # Unlike the public catalog, this intentionally includes inactive
    # products too — the vendor needs to see (and reactivate) them.
    filters.vendor_id = vendor.id
    products, total = await repository.list_products(db, filters=filters, params=params, include_inactive=True)
    rating_map = await reviews_repository.get_rating_summary_map(db, [p.id for p in products])
    for product in products:
        _attach_rating(product, rating_map.get(product.id))
        _attach_delivery_estimate(product)
    return products, total


async def update_product(db: AsyncSession, user: User, product_id: uuid.UUID, data: ProductUpdate) -> Product:
    product = await get_product(db, product_id)
    await _check_product_owner(db, product, user)

    if data.category_id is not None and await repository.get_category_by_id(db, data.category_id) is None:
        raise NotFoundError("Catégorie introuvable.")

    if data.stock is not None and product.variants:
        raise ConflictError("Le stock de ce produit est calculé automatiquement à partir de ses variantes.")

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "description":
            value = _sanitize_description(value)
        setattr(product, field, value)

    await db.commit()
    return await get_product(db, product.id)


async def delete_product(db: AsyncSession, user: User, product_id: uuid.UUID) -> None:
    product = await get_product(db, product_id)
    await _check_product_owner(db, product, user)
    await repository.delete_product(db, product)
    await db.commit()


# --- Product variants ---


async def _sync_product_stock_from_variants(db: AsyncSession, product_id: uuid.UUID) -> None:
    """Maintient Product.stock = somme du stock de ses variantes, dès qu'il en
    a au moins une (voir le commentaire sur ProductVariant dans
    catalog/models.py). Cas limite assumé : supprimer la dernière variante
    remet le stock à 0 (somme sur ensemble vide) — le vendeur doit alors
    ressaisir un stock de base via PATCH /products/{id} s'il repasse en mode
    "sans variante"."""
    total = await repository.sum_variant_stock(db, product_id)
    product = await repository.get_product_by_id(db, product_id)
    if product is not None:
        product.stock = total


async def _get_owned_variant(
    db: AsyncSession, user: User, product_id: uuid.UUID, variant_id: uuid.UUID
) -> tuple[Product, ProductVariant]:
    product = await get_product(db, product_id)
    await _check_product_owner(db, product, user)
    variant = await repository.get_variant_by_id(db, variant_id)
    if variant is None or variant.product_id != product.id:
        raise NotFoundError("Variante introuvable.")
    return product, variant


async def create_variant(
    db: AsyncSession, user: User, product_id: uuid.UUID, data: ProductVariantCreate
) -> ProductVariant:
    product = await get_product(db, product_id)
    await _check_product_owner(db, product, user)

    variant = await repository.create_variant(
        db,
        product_id=product.id,
        sku=data.sku,
        price=data.price,
        stock=data.stock,
        images=data.images,
        attributes=[(a.name, a.value) for a in data.attributes],
    )
    await _sync_product_stock_from_variants(db, product.id)
    await db.commit()
    return await repository.get_variant_by_id(db, variant.id)


async def update_variant(
    db: AsyncSession, user: User, product_id: uuid.UUID, variant_id: uuid.UUID, data: ProductVariantUpdate
) -> ProductVariant:
    product, variant = await _get_owned_variant(db, user, product_id, variant_id)

    updates = data.model_dump(exclude_unset=True, exclude={"attributes"})
    for field, value in updates.items():
        setattr(variant, field, value)
    if data.attributes is not None:
        # Remplacement complet plutôt qu'un diff pair par pair — plus simple
        # et cohérent avec cascade="all, delete-orphan" sur la relation.
        variant.attributes = [ProductVariantAttribute(name=a.name, value=a.value) for a in data.attributes]

    if "stock" in updates:
        await _sync_product_stock_from_variants(db, product.id)

    await db.commit()
    return await repository.get_variant_by_id(db, variant.id)


async def delete_variant(db: AsyncSession, user: User, product_id: uuid.UUID, variant_id: uuid.UUID) -> None:
    product, variant = await _get_owned_variant(db, user, product_id, variant_id)
    await repository.delete_variant(db, variant)
    await db.flush()
    await _sync_product_stock_from_variants(db, product.id)
    await db.commit()
