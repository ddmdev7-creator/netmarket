"""Database access for categories and products."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Category, Product, ProductStatus, ProductVariant, ProductVariantAttribute
from app.catalog.schemas import ProductFilters, ProductSort
from app.core.pagination import PageParams
from app.vendors.models import Vendor

# Seuil de stock faible partagé par le dashboard vendeur (app/vendors/service.py)
# et le filtre "stock_level=low" sur /products/me (app/catalog/repository.py::list_products).
LOW_STOCK_THRESHOLD = 5

# --- Categories ---


async def create_category(db: AsyncSession, *, name: str, parent_id: uuid.UUID | None) -> Category:
    category = Category(name=name, parent_id=parent_id)
    db.add(category)
    await db.flush()
    return category


async def get_category_by_id(db: AsyncSession, category_id: uuid.UUID) -> Category | None:
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def list_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.name))
    return list(result.scalars().all())


async def delete_category(db: AsyncSession, category: Category) -> None:
    await db.delete(category)


# --- Products ---


async def create_product(db: AsyncSession, *, vendor_id: uuid.UUID, **fields) -> Product:
    product = Product(vendor_id=vendor_id, **fields)
    db.add(product)
    await db.flush()
    return product


async def get_product_by_id(db: AsyncSession, product_id: uuid.UUID) -> Product | None:
    stmt = (
        select(Product, Vendor.shop_name, Vendor.zone, Vendor.preparation_days)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .options(selectinload(Product.variants).selectinload(ProductVariant.attributes))
        .where(Product.id == product_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    product, shop_name, vendor_zone, preparation_days = row
    product.vendor_shop_name = shop_name
    product.vendor_zone = vendor_zone
    product.vendor_preparation_days = preparation_days
    return product


async def list_products(
    db: AsyncSession, *, filters: ProductFilters, params: PageParams, include_inactive: bool = False
) -> tuple[list[Product], int]:
    stmt = select(Product)

    if not include_inactive:
        stmt = stmt.where(Product.status == ProductStatus.ACTIVE)
    elif filters.status is not None:
        # Filtre statut explicite (vendeur uniquement, cf. my_product_filters) —
        # remplace le "actif uniquement" par défaut du catalogue public.
        stmt = stmt.where(Product.status == filters.status)
    if filters.vendor_id is not None:
        stmt = stmt.where(Product.vendor_id == filters.vendor_id)
    if filters.category_id is not None:
        stmt = stmt.where(Product.category_id == filters.category_id)
    if filters.min_price is not None:
        stmt = stmt.where(Product.price >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(Product.price <= filters.max_price)
    if filters.in_stock is not None:
        stmt = stmt.where(Product.stock > 0) if filters.in_stock else stmt.where(Product.stock == 0)
    if filters.stock_level == "out":
        stmt = stmt.where(Product.stock == 0)
    elif filters.stock_level == "low":
        stmt = stmt.where(Product.stock > 0, Product.stock <= LOW_STOCK_THRESHOLD)
    if filters.q:
        stmt = stmt.where(Product.name.ilike(f"%{filters.q}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    order_by = {
        ProductSort.PRICE_ASC: Product.price.asc(),
        ProductSort.PRICE_DESC: Product.price.desc(),
        ProductSort.RECENT: Product.created_at.desc(),
    }[filters.sort]

    paged_stmt = (
        stmt.join(Vendor, Product.vendor_id == Vendor.id)
        .add_columns(Vendor.shop_name, Vendor.zone, Vendor.preparation_days)
        .options(selectinload(Product.variants).selectinload(ProductVariant.attributes))
        .order_by(order_by)
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = (await db.execute(paged_stmt)).all()
    products = []
    for product, shop_name, vendor_zone, preparation_days in rows:
        product.vendor_shop_name = shop_name
        product.vendor_zone = vendor_zone
        product.vendor_preparation_days = preparation_days
        products.append(product)
    return products, total


async def delete_product(db: AsyncSession, product: Product) -> None:
    await db.delete(product)


async def count_active_products_for_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Product).where(
        Product.vendor_id == vendor_id, Product.status == ProductStatus.ACTIVE
    )
    return (await db.execute(stmt)).scalar_one()


async def list_low_stock_products(db: AsyncSession, vendor_id: uuid.UUID, threshold: int) -> list[Product]:
    stmt = (
        select(Product)
        .where(
            Product.vendor_id == vendor_id,
            Product.status == ProductStatus.ACTIVE,
            Product.stock <= threshold,
        )
        .order_by(Product.stock)
    )
    return list((await db.execute(stmt)).scalars().all())


# --- Product variants ---


async def create_variant(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    sku: str | None,
    price: int | None,
    stock: int,
    images: list[str] | None,
    attributes: list[tuple[str, str]],
) -> ProductVariant:
    variant = ProductVariant(product_id=product_id, sku=sku, price=price, stock=stock, images=images)
    variant.attributes = [ProductVariantAttribute(name=name, value=value) for name, value in attributes]
    db.add(variant)
    await db.flush()
    return variant


async def get_variant_by_id(db: AsyncSession, variant_id: uuid.UUID) -> ProductVariant | None:
    stmt = (
        select(ProductVariant)
        .options(selectinload(ProductVariant.attributes))
        .where(ProductVariant.id == variant_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def delete_variant(db: AsyncSession, variant: ProductVariant) -> None:
    await db.delete(variant)


async def sum_variant_stock(db: AsyncSession, product_id: uuid.UUID) -> int:
    stmt = select(func.coalesce(func.sum(ProductVariant.stock), 0)).where(ProductVariant.product_id == product_id)
    return (await db.execute(stmt)).scalar_one()
