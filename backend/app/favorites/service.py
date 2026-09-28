"""Favoris + alertes « prix en baisse » / « de nouveau en stock »."""

import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog_service
from app.catalog.models import Product, ProductStatus
from app.core.exceptions import NotFoundError
from app.favorites.models import Favorite
from app.users.models import User

logger = logging.getLogger(__name__)


def display_price(product: Product) -> int:
    """Prix d'appel d'un produit (le moins cher de ses variantes s'il en a) —
    le même que la carte produit affiche après « dès »."""
    prices = [v.price if v.price is not None else product.price for v in product.variants]
    return min(prices) if prices else product.price


async def list_ids(db: AsyncSession, user: User) -> list[uuid.UUID]:
    rows = await db.execute(
        select(Favorite.product_id).where(Favorite.user_id == user.id).order_by(Favorite.created_at.desc())
    )
    return list(rows.scalars().all())


async def list_favorites(db: AsyncSession, user: User) -> list[dict]:
    favorites = (
        await db.execute(select(Favorite).where(Favorite.user_id == user.id).order_by(Favorite.created_at.desc()))
    ).scalars().all()
    result = []
    for favorite in favorites:
        try:
            product = await catalog_service.get_product(db, favorite.product_id)
        except NotFoundError:
            continue
        if product.status != ProductStatus.ACTIVE:
            continue
        result.append({"product": product, "price_at_add": favorite.price_at_add, "created_at": favorite.created_at})
    return result


async def add(db: AsyncSession, user: User, product_id: uuid.UUID) -> None:
    product = await catalog_service.get_product(db, product_id)
    existing = await db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id)
    )
    if existing is None:
        price = display_price(product)
        db.add(Favorite(user_id=user.id, product_id=product_id, price_at_add=price, alerted_price=price))
        await db.commit()


async def remove(db: AsyncSession, user: User, product_id: uuid.UUID) -> None:
    await db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    await db.commit()


async def on_product_changed(db: AsyncSession, product_id: uuid.UUID, before: tuple[int, int] | None) -> None:
    """Prévient les acheteurs qui ont ce produit en favori d'une baisse de prix
    ou d'un retour en stock. Jamais bloquant pour le vendeur : une erreur ici
    est seulement journalisée."""
    if before is None:
        return
    try:
        await _notify_changes(db, product_id, before)
    except Exception:  # noqa: BLE001 - l'enregistrement du produit est déjà fait
        logger.exception("Échec des alertes favoris pour le produit %s", product_id)


async def _notify_changes(db: AsyncSession, product_id: uuid.UUID, before: tuple[int, int]) -> None:
    from app.notifications import service as notifications_service

    old_price, old_stock = before
    product = await catalog_service.get_product(db, product_id)
    if product.status != ProductStatus.ACTIVE:
        return
    new_price, new_stock = display_price(product), product.stock
    price_dropped = new_price < old_price
    back_in_stock = old_stock == 0 and new_stock > 0
    if not price_dropped and not back_in_stock:
        return

    rows = (
        await db.execute(select(Favorite, User).join(User, User.id == Favorite.user_id).where(Favorite.product_id == product_id))
    ).all()
    for favorite, user in rows:
        if price_dropped and new_price < favorite.alerted_price:
            favorite.alerted_price = new_price
            await notifications_service.notify_favorite_price_drop(
                db, user=user, product=product, old_price=old_price, new_price=new_price
            )
        elif back_in_stock:
            favorite.back_in_stock_alerted_at = func.now()
            await notifications_service.notify_favorite_back_in_stock(db, user=user, product=product)
    await db.commit()


