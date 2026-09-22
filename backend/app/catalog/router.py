"""Category and product endpoints: public catalog browsing + vendor/admin CRUD."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service
from app.catalog.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    ProductCreate,
    ProductFilters,
    ProductRead,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantRead,
    ProductVariantUpdate,
    my_product_filters,
    product_filters,
)
from app.common.schemas import Message
from app.core.deps import get_current_user, get_db, require_role
from app.core.pagination import Page, PageParams, pagination_params
from app.users.models import User, UserRole

router = APIRouter(tags=["catalog"])

# --- Categories ---


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def create_category(payload: CategoryCreate, db: AsyncSession = Depends(get_db)) -> CategoryRead:
    return await service.create_category(db, payload)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryRead,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def update_category(
    category_id: uuid.UUID, payload: CategoryUpdate, db: AsyncSession = Depends(get_db)
) -> CategoryRead:
    return await service.update_category(db, category_id, payload)


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[CategoryRead]:
    return await service.list_categories(db)


@router.delete(
    "/categories/{category_id}",
    response_model=Message,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_category(category_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Message:
    await service.delete_category(db, category_id)
    return Message(detail="Catégorie supprimée.")


# --- Products ---


@router.post(
    "/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.VENDOR))],
)
async def create_product(
    payload: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    return await service.create_product(db, current_user, payload)


@router.get("/products", response_model=Page[ProductRead])
async def list_products(
    filters: ProductFilters = Depends(product_filters),
    params: PageParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
) -> Page[ProductRead]:
    items, total = await service.list_products(db, filters, params)
    return Page.create(items=items, total=total, params=params)


@router.get(
    "/products/me",
    response_model=Page[ProductRead],
    dependencies=[Depends(require_role(UserRole.VENDOR))],
)
async def list_my_products(
    filters: ProductFilters = Depends(my_product_filters),
    params: PageParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[ProductRead]:
    items, total = await service.list_my_products(db, current_user, params, filters)
    return Page.create(items=items, total=total, params=params)


@router.get("/products/{product_id}", response_model=ProductRead)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProductRead:
    return await service.get_product(db, product_id)


@router.patch(
    "/products/{product_id}",
    response_model=ProductRead,
    dependencies=[Depends(require_role(UserRole.VENDOR, UserRole.ADMIN))],
)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    return await service.update_product(db, current_user, product_id, payload)


@router.delete(
    "/products/{product_id}",
    response_model=Message,
    dependencies=[Depends(require_role(UserRole.VENDOR, UserRole.ADMIN))],
)
async def delete_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Message:
    await service.delete_product(db, current_user, product_id)
    return Message(detail="Produit supprimé.")


# --- Product variants (imbriquées sous le produit, pas de GET dédié — toujours
# lues via GET /products/{id}) ---


@router.post(
    "/products/{product_id}/variants",
    response_model=ProductVariantRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.VENDOR, UserRole.ADMIN))],
)
async def create_variant(
    product_id: uuid.UUID,
    payload: ProductVariantCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductVariantRead:
    return await service.create_variant(db, current_user, product_id, payload)


@router.patch(
    "/products/{product_id}/variants/{variant_id}",
    response_model=ProductVariantRead,
    dependencies=[Depends(require_role(UserRole.VENDOR, UserRole.ADMIN))],
)
async def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: ProductVariantUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductVariantRead:
    return await service.update_variant(db, current_user, product_id, variant_id, payload)


@router.delete(
    "/products/{product_id}/variants/{variant_id}",
    response_model=Message,
    dependencies=[Depends(require_role(UserRole.VENDOR, UserRole.ADMIN))],
)
async def delete_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Message:
    await service.delete_variant(db, current_user, product_id, variant_id)
    return Message(detail="Variante supprimée.")
