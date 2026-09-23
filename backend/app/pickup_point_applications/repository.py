"""Accès base des candidatures gestionnaire de point de retrait."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pickup_point_applications.models import ApplicationStatus, PickupPointApplication

# Clés produites par service.upload_documents (préfixe dédié, jamais servi publiquement).
KEY_PATTERN = re.compile(r"^pickup-applications/[0-9a-f-]{36}\.jpg$")


def add(db: AsyncSession, application: PickupPointApplication) -> None:
    db.add(application)


async def get_by_id(
    db: AsyncSession, application_id: uuid.UUID, *, for_update: bool = False
) -> PickupPointApplication | None:
    stmt = select(PickupPointApplication).where(PickupPointApplication.id == application_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_by_user_id(
    db: AsyncSession, user_id: uuid.UUID, *, for_update: bool = False
) -> PickupPointApplication | None:
    stmt = select(PickupPointApplication).where(PickupPointApplication.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_all(db: AsyncSession, status: ApplicationStatus | None) -> list[PickupPointApplication]:
    stmt = select(PickupPointApplication).order_by(
        PickupPointApplication.submitted_at.desc().nulls_last(), PickupPointApplication.updated_at.desc()
    )
    if status is not None:
        stmt = stmt.where(PickupPointApplication.status == status)
    return list((await db.execute(stmt.limit(300))).scalars().all())
