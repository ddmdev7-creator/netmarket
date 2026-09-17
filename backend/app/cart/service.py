"""Cart business logic: add/update/remove items, and the grouped-by-vendor view."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart import repository
from app.cart.models import CartItem
from app.cart.schemas import CartItemCreate, CartItemRead, CartItemUpdate, CartRead, VendorCartGroup
from app.catalog import repository as catalog_repository
from app.catalog.models import ProductStatus
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.users.models import User


async def add_item(db: AsyncSession, user: User, data: CartItemCreate) -> None:
    product = await catalog_repository.get_product_by_id(db, data.product_id)
    if product is None:
        raise NotFoundError("Produit introuvable.")
    if product.status != ProductStatus.ACTIVE:
        raise ConflictError("Ce produit n'est plus disponible.")

    if product.variants:
        if data.variant_id is None:
            raise ConflictError("Merci de choisir une variante avant d'ajouter ce produit au panier.")
        if not any(v.id == data.variant_id for v in product.variants):
            raise NotFoundError("Variante introuvable pour ce produit.")
    elif data.variant_id is not None:
        raise ConflictError("Ce produit ne propose pas de variantes.")

    existing = await repository.get_item_by_product_and_variant(db, user.id, data.product_id, data.variant_id)
    if existing is not None:
        existing.quantity += data.quantity
    else:
        await repository.create_item(
            db, user_id=user.id, product_id=data.product_id, variant_id=data.variant_id, quantity=data.quantity
        )

    await db.commit()


async def update_item(db: AsyncSession, user: User, item_id: uuid.UUID, data: CartItemUpdate) -> None:
    item = await _get_own_item(db, user, item_id)
    item.quantity = data.quantity
    await db.commit()


async def remove_item(db: AsyncSession, user: User, item_id: uuid.UUID) -> None:
    item = await _get_own_item(db, user, item_id)
    await repository.delete_item(db, item)
    await db.commit()


async def clear_cart(db: AsyncSession, user: User) -> None:
    await repository.clear_for_user(db, user.id)
    await db.commit()


async def get_cart(db: AsyncSession, user: User) -> CartRead:
    rows = await repository.list_items_with_product_variant_and_vendor(db, user.id)

    groups: dict[uuid.UUID, VendorCartGroup] = {}
    total = 0
    for cart_item, product, variant, vendor in rows:
        unit_price = variant.price if (variant is not None and variant.price is not None) else product.price
        subtotal = unit_price * cart_item.quantity
        total += subtotal
        images = (variant.images if (variant is not None and variant.images) else None) or product.images
        item_read = CartItemRead(
            id=cart_item.id,
            product_id=product.id,
            variant_id=variant.id if variant is not None else None,
            variant_label=variant.label() if variant is not None else None,
            product_name=product.name,
            product_image=images[0] if images else None,
            unit_price=unit_price,
            quantity=cart_item.quantity,
            subtotal=subtotal,
        )
        group = groups.get(vendor.id)
        if group is None:
            group = VendorCartGroup(vendor_id=vendor.id, shop_name=vendor.shop_name, items=[], subtotal=0)
            groups[vendor.id] = group
        group.items.append(item_read)
        group.subtotal += subtotal

    return CartRead(vendors=list(groups.values()), total=total)


async def _get_own_item(db: AsyncSession, user: User, item_id: uuid.UUID) -> CartItem:
    item = await repository.get_item_by_id(db, item_id)
    if item is None:
        raise NotFoundError("Article du panier introuvable.")
    if item.user_id != user.id:
        raise ForbiddenError("Cet article ne fait pas partie de votre panier.")
    return item
