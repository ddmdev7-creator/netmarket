"""Review creation, gated on the buyer having actually received the product."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository as catalog_repository
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.orders import repository as orders_repository
from app.reviews import repository
from app.reviews.models import Review
from app.reviews.schemas import ReviewableProductRead, ReviewCreate, ReviewRead, ReviewUpdate
from app.users.models import User


def _author_name(user: User | None) -> str | None:
    if user is None or not user.first_name:
        return None
    return f"{user.first_name} {user.last_name[0].upper()}." if user.last_name else user.first_name


def _to_read(review: Review, author: User | None) -> ReviewRead:
    read = ReviewRead.model_validate(review)
    read.author_name = _author_name(author)
    return read


async def create_review(db: AsyncSession, user: User, product_id: uuid.UUID, data: ReviewCreate) -> ReviewRead:
    user_id = user.id
    if not await orders_repository.has_delivered_product_for_user(db, user_id, product_id):
        raise ForbiddenError("Vous ne pouvez laisser un avis que sur un produit que vous avez reçu.")

    if await repository.get_by_product_and_user(db, product_id, user_id) is not None:
        raise ConflictError("Vous avez déjà laissé un avis pour ce produit.")

    review = await repository.create(
        db, product_id=product_id, user_id=user_id, rating=data.rating, comment=data.comment
    )
    await db.commit()
    await db.refresh(review)
    return _to_read(review, user)


async def update_my_review(db: AsyncSession, user: User, product_id: uuid.UUID, data: ReviewUpdate) -> ReviewRead:
    review = await repository.get_by_product_and_user(db, product_id, user.id)
    if review is None:
        raise NotFoundError("Vous n'avez pas encore laissé d'avis pour ce produit.")
    review.rating = data.rating
    review.comment = data.comment
    await db.commit()
    await db.refresh(review)
    return _to_read(review, user)


async def list_reviews_for_product(db: AsyncSession, product_id: uuid.UUID) -> list[ReviewRead]:
    return [_to_read(review, author) for review, author in await repository.list_for_product(db, product_id)]


async def list_reviewable_products(db: AsyncSession, user: User) -> list[ReviewableProductRead]:
    """Chaque produit reçu une fois (la livraison la plus récente), avec
    l'avis de l'acheteur s'il existe — les produits pas encore notés d'abord."""
    latest: dict[uuid.UUID, tuple] = {}
    for product_id, product_name, variant_id, order_id, delivered_at in await orders_repository.list_delivered_items_for_user(
        db, user.id
    ):
        latest.setdefault(product_id, (product_name, variant_id, order_id, delivered_at))

    reviews = await repository.list_for_user_and_products(db, user.id, list(latest))
    result = []
    for product_id, (frozen_name, variant_id, order_id, delivered_at) in latest.items():
        # Nom et photo actuels du produit (même logique que
        # app/orders/service.py::_attach_product_images), le nom figé au
        # checkout en repli si le produit a disparu.
        product = await catalog_repository.get_product_by_id(db, product_id)
        variant = await catalog_repository.get_variant_by_id(db, variant_id) if variant_id and product else None
        images = ((variant.images if variant is not None and variant.images else None) or product.images) if product else []
        review = reviews.get(product_id)
        result.append(
            ReviewableProductRead(
                product_id=product_id,
                product_name=product.name if product else frozen_name,
                product_image=images[0] if images else None,
                order_id=order_id,
                delivered_at=delivered_at,
                review=_to_read(review, user) if review else None,
            )
        )
    result.sort(key=lambda r: r.review is not None)
    return result
