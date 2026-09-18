"""Common FastAPI dependencies: DB session, current user, role guard."""

import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.users.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Authentification requise.")

    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
        user_id = uuid.UUID(payload["sub"])
    except (InvalidTokenError, ValueError) as exc:
        raise UnauthorizedError("Session invalide ou expirée, veuillez vous reconnecter.") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("Compte introuvable ou désactivé.")

    return user


def require_role(*roles: UserRole) -> Callable[[User], Coroutine[None, None, User]]:
    """Build a dependency that only lets the given roles through, e.g. Depends(require_role(UserRole.ADMIN))."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ForbiddenError("Vous n'avez pas les droits nécessaires pour effectuer cette action.")
        return user

    return dependency


async def get_pickup_point_manager(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> User:
    """Gate for pickup-point-manager-only endpoints that checks for an actual
    PickupPointManager row instead of user.role == PICKUP_POINT_MANAGER —
    lets a vendor whose shop IS a pickup point (PickupPoint.vendor_id) act as
    that point's manager with their existing vendor account, without touching
    their role (see app/pickup_point_managers/service.py::admin_link_vendor_as_manager).
    Import kept local to dodge a module-level cycle with app.pickup_point_managers.repository."""
    from app.pickup_point_managers import repository as pickup_point_manager_repository

    manager = await pickup_point_manager_repository.get_by_user_id(db, user.id)
    if manager is None:
        raise ForbiddenError("Vous n'avez pas les droits nécessaires pour effectuer cette action.")
    return user
