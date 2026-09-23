"""Business logic for pickup point manager accounts — admin-only creation
and management (see app/pickup_point_managers/models.py for why there's no
self-registration/approval lifecycle here, unlike couriers)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.pickup_point_managers import repository
from app.pickup_point_managers.models import PickupPointManager
from app.pickup_point_managers.schemas import (
    ManagerPointUpdate,
    PickupPointManagerAdminCreate,
    PickupPointManagerAdminUpdate,
)
from app.pickup_points import repository as pickup_points_repository
from app.users import repository as users_repository
from app.users.models import User, UserRole
from app.vendors import repository as vendor_repository


async def _ensure_active_point(db: AsyncSession, pickup_point_id: uuid.UUID) -> None:
    point = await pickup_points_repository.get_by_id(db, pickup_point_id)
    if point is None or not point.is_active:
        raise ConflictError("Ce point de retrait n'est pas disponible.")


async def admin_create_manager(db: AsyncSession, data: PickupPointManagerAdminCreate) -> PickupPointManager:
    if await users_repository.get_by_phone(db, data.phone) is not None:
        raise ConflictError("Ce numéro de téléphone est déjà utilisé.")
    await _ensure_active_point(db, data.pickup_point_id)

    user = await users_repository.create(
        db,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.PICKUP_POINT_MANAGER,
        first_name=data.first_name,
        last_name=data.last_name,
    )
    manager = await repository.create(db, user_id=user.id, pickup_point_id=data.pickup_point_id)
    await db.commit()
    return await repository.get_by_id(db, manager.id)


async def admin_link_vendor_as_manager(db: AsyncSession, pickup_point_id: uuid.UUID) -> PickupPointManager:
    """Lets the vendor whose shop IS this pickup point (PickupPoint.vendor_id)
    also manage it, with their existing vendor login — no new account, no
    change to their role (see app/core/deps.py::get_pickup_point_manager,
    which authorizes on this row's existence rather than on user.role)."""
    point = await pickup_points_repository.get_by_id(db, pickup_point_id)
    if point is None:
        raise NotFoundError("Point de retrait introuvable.")
    if point.vendor_id is None:
        raise ConflictError("Ce point de retrait n'est pas lié à une boutique.")

    vendor = await vendor_repository.get_by_id(db, point.vendor_id)
    if vendor is None:
        raise NotFoundError("Boutique introuvable.")

    existing = await repository.list_by_pickup_point(db, pickup_point_id)
    already_linked = next((m for m in existing if m.user_id == vendor.user_id), None)
    if already_linked is not None:
        return already_linked

    manager = await repository.create(db, user_id=vendor.user_id, pickup_point_id=pickup_point_id)
    await db.commit()
    return await repository.get_by_id(db, manager.id)


async def admin_list_managers(db: AsyncSession, pickup_point_id: uuid.UUID | None) -> list[PickupPointManager]:
    return await repository.list_by_pickup_point(db, pickup_point_id)


async def admin_update_manager(
    db: AsyncSession, manager_id: uuid.UUID, data: PickupPointManagerAdminUpdate
) -> PickupPointManager:
    manager = await repository.get_by_id(db, manager_id)
    if manager is None:
        raise NotFoundError("Gestionnaire introuvable.")
    if data.pickup_point_id is not None:
        await _ensure_active_point(db, data.pickup_point_id)
        manager.pickup_point_id = data.pickup_point_id
    await db.commit()
    return await repository.get_by_id(db, manager_id)


async def admin_delete_manager(db: AsyncSession, manager_id: uuid.UUID) -> None:
    manager = await repository.get_by_id(db, manager_id)
    if manager is None:
        raise NotFoundError("Gestionnaire introuvable.")
    await repository.delete(db, manager)
    await db.commit()


async def get_my_manager_profile(db: AsyncSession, user: User) -> PickupPointManager:
    manager = await repository.get_by_user_id(db, user.id)
    if manager is None:
        raise NotFoundError("Vous n'avez pas de profil gestionnaire de point de retrait.")
    return manager


async def get_my_point(db: AsyncSession, user: User):
    manager = await repository.get_by_user_id(db, user.id)
    if manager is None:
        raise NotFoundError("Vous n'avez pas de profil gestionnaire de point de retrait.")
    point = await pickup_points_repository.get_by_id(db, manager.pickup_point_id)
    if point is None:
        raise NotFoundError("Point de retrait introuvable.")
    point.average_rating, point.review_count = await pickup_points_repository.get_rating_summary(db, point.id)
    return point


async def update_my_point(db: AsyncSession, user: User, data: ManagerPointUpdate):
    point = await get_my_point(db, user)
    point.opening_hours = data.opening_hours.strip()
    await db.commit()
    return await get_my_point(db, user)
