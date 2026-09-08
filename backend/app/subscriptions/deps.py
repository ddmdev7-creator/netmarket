"""Dependency gating endpoints behind an active vendor subscription."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.core.exceptions import ForbiddenError
from app.subscriptions import service
from app.users.models import User, UserRole
from app.vendors import service as vendors_service
from app.vendors.models import Vendor


async def require_premium_vendor(
    current_user: User = Depends(require_role(UserRole.VENDOR)), db: AsyncSession = Depends(get_db)
) -> Vendor:
    vendor = await vendors_service.get_my_vendor(db, current_user)
    if not await service.is_premium(db, vendor.id):
        raise ForbiddenError("Fonctionnalité réservée aux vendeurs avec un abonnement premium actif.")
    return vendor
