"""Database access for Notification."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification

# Un utilisateur ne consulte réalistement que ses notifications récentes — pas
# de pagination complète, juste les N dernières (badge + liste déroulante).
MAX_LISTED = 50


async def create(db: AsyncSession, **fields) -> Notification:
    notification = Notification(**fields)
    db.add(notification)
    await db.flush()
    return notification


async def get_by_id(db: AsyncSession, notification_id: uuid.UUID) -> Notification | None:
    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    return result.scalar_one_or_none()


async def list_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(MAX_LISTED)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_unread(db: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, Notification.read_at.is_(None)
    )
    return (await db.execute(stmt)).scalar_one()


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )


async def delete_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        delete(Notification).where(Notification.user_id == user_id, Notification.read_at.is_not(None))
    )
    return result.rowcount or 0
