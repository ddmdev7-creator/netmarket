"""Rappel « vos articles vous attendent » pour les paniers laissés de côté,
envoyé par la tâche périodique lancée au démarrage de l'API (app/main.py)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.models import CartItem
from app.core.database import AsyncSessionLocal
from app.users.models import User, UserRole

logger = logging.getLogger(__name__)

# Panier inchangé depuis au moins IDLE, mais pas plus vieux que STALE (au-delà,
# un rappel tomberait à plat).
IDLE = timedelta(hours=24)
STALE = timedelta(days=7)
INTERVAL_SECONDS = 30 * 60


async def send_cart_reminders(db: AsyncSession, *, now: datetime | None = None) -> int:
    from app.notifications import service as notifications_service

    now = now or datetime.now(UTC)
    carts = (
        select(
            CartItem.user_id,
            func.max(CartItem.updated_at).label("last_change"),
            func.sum(CartItem.quantity).label("item_count"),
        )
        .group_by(CartItem.user_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(User, carts.c.item_count)
            .join(carts, carts.c.user_id == User.id)
            .where(
                User.is_active.is_(True),
                User.role == UserRole.BUYER,
                carts.c.last_change <= now - IDLE,
                carts.c.last_change >= now - STALE,
                or_(User.cart_reminder_sent_at.is_(None), User.cart_reminder_sent_at < carts.c.last_change),
            )
        )
    ).all()
    for user, item_count in rows:
        user.cart_reminder_sent_at = now
        await notifications_service.notify_cart_reminder(db, user=user, item_count=int(item_count))
    await db.commit()
    return len(rows)


async def run_forever() -> None:
    """Boucle de fond (une seule instance d'API tourne, voir app/main.py)."""
    while True:
        await asyncio.sleep(INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                sent = await send_cart_reminders(db)
            if sent:
                logger.info("Rappels panier envoyés : %s", sent)
        except Exception:  # noqa: BLE001 - la boucle doit survivre à une erreur ponctuelle
            logger.exception("Échec de la tâche de rappel panier")
