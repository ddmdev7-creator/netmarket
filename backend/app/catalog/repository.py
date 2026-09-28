"""Database access for categories and products."""

import math
import uuid

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Category, Product, ProductStatus, ProductVariant, ProductVariantAttribute
from app.catalog.schemas import ProductFilters, ProductSort
from app.core.pagination import PageParams
from app.reviews.models import Review
from app.vendors.models import Vendor

# Seuil de stock faible partagé par le dashboard vendeur (app/vendors/service.py)
# et le filtre "stock_level=low" sur /products/me (app/catalog/repository.py::list_products).
LOW_STOCK_THRESHOLD = 5

# --- Categories ---


async def create_category(
    db: AsyncSession, *, name: str, parent_id: uuid.UUID | None, icon: str | None = None
) -> Category:
    category = Category(name=name, parent_id=parent_id, icon=icon)
    db.add(category)
    await db.flush()
    return category


async def get_category_by_id(db: AsyncSession, category_id: uuid.UUID) -> Category | None:
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def list_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.name))
    return list(result.scalars().all())


def category_subtree_ids(category_id: uuid.UUID):
    """Sous-requête des ids de la catégorie et de toutes ses descendantes — filtrer
    sur une catégorie parente ("Ordinateur") montre aussi ses sous-catégories
    ("Hp", "Lenovo"), sinon une catégorie racine sans produit direct paraît vide."""
    tree = select(Category.id).where(Category.id == category_id).cte("category_tree", recursive=True)
    tree = tree.union_all(select(Category.id).where(Category.parent_id == tree.c.id))
    return select(tree.c.id)


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


# --- Recherche -----------------------------------------------------------------

_ACCENTED = "àâäáãåçéèêëíìîïñóòôöõúùûüýÿœÀÂÄÁÃÅÇÉÈÊËÍÌÎÏÑÓÒÔÖÕÚÙÛÜÝ"
_PLAIN = "aaaaaaceeeeiiiinooooouuuuyyoAAAAAACEEEEIIIINOOOOOUUUUY"


def normalize_text(text: str) -> str:
    """Pendant Python de normalized() : minuscules, sans accents."""
    return text.translate(str.maketrans(_ACCENTED, _PLAIN)).lower()


def normalized(column):
    """Colonne en minuscules et sans accents : "electronique" trouve "Électronique"
    (translate() plutôt que l'extension unaccent, qui demande des droits superutilisateur)."""
    return func.lower(func.translate(column, _ACCENTED, _PLAIN))


def search_tokens(q: str | None) -> list[str]:
    """Mots de la recherche, normalisés et échappés pour LIKE (au plus 6)."""
    if not q:
        return []
    words = [normalize_text(w) for w in q.split() if w.strip()]
    return [w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for w in words][:6]


def _search_clause(tokens: list[str]):
    """Chaque mot doit apparaître dans le nom du produit ou de sa catégorie
    ("hp portable" trouve "Ordinateur Portable HP"). Le nom de la boutique
    n'en fait pas partie : "elec" remonterait sinon tout le catalogue de
    "Electronic Center" — la boutique est proposée à part (suggest)."""
    clauses = []
    for token in tokens:
        pattern = f"%{token}%"
        matching_categories = select(Category.id).where(normalized(Category.name).like(pattern))
        clauses.append(
            or_(
                normalized(Product.name).like(pattern),
                Product.category_id.in_(matching_categories),
            )
        )
    return and_(*clauses)


async def list_products(
    db: AsyncSession, *, filters: ProductFilters, params: PageParams, include_inactive: bool = False
) -> tuple[list[Product], int]:
    stmt = select(Product).join(Vendor, Product.vendor_id == Vendor.id)

    if not include_inactive:
        stmt = stmt.where(Product.status == ProductStatus.ACTIVE)
    elif filters.status is not None:
        # Filtre statut explicite (vendeur uniquement, cf. my_product_filters) —
        # remplace le "actif uniquement" par défaut du catalogue public.
        stmt = stmt.where(Product.status == filters.status)
    if filters.vendor_id is not None:
        stmt = stmt.where(Product.vendor_id == filters.vendor_id)
    if filters.category_id is not None:
        stmt = stmt.where(Product.category_id.in_(category_subtree_ids(filters.category_id)))
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
    tokens = search_tokens(filters.q)
    if tokens:
        stmt = stmt.where(_search_clause(tokens))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    paged_stmt = stmt
    order_by: list = []
    if tokens and filters.sort == ProductSort.RECENT:
        # Recherche sans tri explicite : les produits dont le NOM contient la
        # recherche passent avant ceux trouvés via la catégorie ou la boutique,
        # et ceux dont le nom COMMENCE par le premier mot avant tout.
        name = normalized(Product.name)
        order_by = [
            case((name.like(f"{tokens[0]}%"), 0), else_=1),
            case((and_(*[name.like(f"%{t}%") for t in tokens]), 0), else_=1),
        ]
    if filters.sort == ProductSort.TOP_RATED:
        ratings = (
            select(Review.product_id, func.avg(Review.rating).label("avg"), func.count(Review.id).label("n"))
            .group_by(Review.product_id)
            .subquery()
        )
        paged_stmt = paged_stmt.outerjoin(ratings, ratings.c.product_id == Product.id)
        order_by = [ratings.c.avg.desc().nulls_last(), ratings.c.n.desc().nulls_last()]
    elif filters.sort == ProductSort.NEAREST and filters.near_lat is not None and filters.near_lng is not None:
        # Distance "à plat" (longitude corrigée par cos(lat)) : suffisante pour
        # classer des boutiques à l'échelle d'une ville.
        lng_scale = math.cos(math.radians(filters.near_lat))
        distance = func.pow(Vendor.latitude - filters.near_lat, 2) + func.pow(
            (Vendor.longitude - filters.near_lng) * lng_scale, 2
        )
        order_by = [distance.asc().nulls_last()]
    elif filters.sort == ProductSort.PRICE_ASC:
        order_by = [Product.price.asc()]
    elif filters.sort == ProductSort.PRICE_DESC:
        order_by = [Product.price.desc()]
    # Départage stable (sinon offset/limit peut répéter ou sauter des produits
    # d'une page à l'autre en défilement infini).
    order_by += [Product.created_at.desc(), Product.id]

    paged_stmt = (
        paged_stmt.add_columns(Vendor.shop_name, Vendor.zone, Vendor.preparation_days)
        .options(selectinload(Product.variants).selectinload(ProductVariant.attributes))
        .order_by(*order_by)
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


async def suggest(db: AsyncSession, q: str, *, limit: int = 5) -> dict:
    """Suggestions de la barre de recherche : produits, catégories, boutiques."""
    tokens = search_tokens(q)
    if not tokens:
        return {"products": [], "categories": [], "shops": []}
    name = normalized(Product.name)
    product_rows = (
        await db.execute(
            select(Product.id, Product.name, Product.price, Product.images)
            .join(Vendor, Product.vendor_id == Vendor.id)
            .where(Product.status == ProductStatus.ACTIVE, _search_clause(tokens))
            .order_by(
                case((name.like(f"{tokens[0]}%"), 0), else_=1),
                case((and_(*[name.like(f"%{t}%") for t in tokens]), 0), else_=1),
                Product.created_at.desc(),
            )
            .limit(limit)
        )
    ).all()
    category_clause = and_(*[normalized(Category.name).like(f"%{t}%") for t in tokens])
    categories = (
        await db.execute(select(Category).where(category_clause).order_by(Category.name).limit(limit))
    ).scalars().all()
    shop_clause = and_(*[normalized(Vendor.shop_name).like(f"%{t}%") for t in tokens])
    shops = (
        await db.execute(
            select(Vendor.id, Vendor.shop_name, func.count(Product.id))
            .join(Product, and_(Product.vendor_id == Vendor.id, Product.status == ProductStatus.ACTIVE))
            .where(shop_clause)
            .group_by(Vendor.id, Vendor.shop_name)
            .order_by(Vendor.shop_name)
            .limit(3)
        )
    ).all()
    return {
        "products": [
            {"id": pid, "name": pname, "price": price, "image": (images or [None])[0]}
            for pid, pname, price, images in product_rows
        ],
        "categories": categories,
        "shops": [{"id": vid, "shop_name": shop, "product_count": count} for vid, shop, count in shops],
    }


async def search_vocabulary(db: AsyncSession) -> list[str]:
    """Mots connus du catalogue (noms de produits actifs, catégories, boutiques)
    — base du "Vouliez-vous dire…" quand une recherche ne donne rien."""
    rows = (
        await db.execute(select(Product.name).where(Product.status == ProductStatus.ACTIVE).limit(5000))
    ).scalars().all()
    rows += (await db.execute(select(Category.name))).scalars().all()
    rows += (await db.execute(select(Vendor.shop_name))).scalars().all()
    return rows
