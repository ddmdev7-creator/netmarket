"""Vendor onboarding, own-profile management, public directory, and admin validation.

Admin endpoints live under /admin/vendors (distinct namespace) rather than
/vendors/{id} to avoid routing ambiguity and to anticipate the dedicated
admin module (moderation/commissions/stats) planned for a later iteration.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.users.models import User, UserRole
from app.vendors import service
from app.vendors.models import VendorStatus
from app.vendors.schemas import (
    DailyOrderCount,
    VendorAdminUpdate,
    VendorDashboard,
    VendorOwnerUpdate,
    VendorPublicRead,
    VendorRead,
    VendorRegister,
)

router = APIRouter(prefix="/vendors", tags=["vendors"])
admin_router = APIRouter(prefix="/admin/vendors", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.post("/me", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
async def register_vendor(
    payload: VendorRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VendorRead:
    return await service.register_vendor(db, current_user, payload)


@router.get("/me", response_model=VendorRead)
async def get_my_vendor(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> VendorRead:
    return await service.get_my_vendor(db, current_user)


@router.patch("/me", response_model=VendorRead)
async def update_my_vendor(
    payload: VendorOwnerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VendorRead:
    return await service.update_my_vendor(db, current_user, payload)


@router.get("/me/dashboard", response_model=VendorDashboard)
async def get_my_dashboard(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> VendorDashboard:
    return await service.get_my_dashboard(db, current_user)


@router.get("/me/orders-timeseries", response_model=list[DailyOrderCount])
async def get_my_orders_timeseries(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[DailyOrderCount]:
    return await service.get_my_orders_timeseries(db, current_user)


@router.get("", response_model=list[VendorPublicRead])
async def list_vendors(db: AsyncSession = Depends(get_db)) -> list[VendorPublicRead]:
    return await service.list_public_vendors(db)


@router.get("/{vendor_id}", response_model=VendorPublicRead)
async def get_vendor(vendor_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> VendorPublicRead:
    return await service.get_public_vendor(db, vendor_id)


@admin_router.get("", response_model=list[VendorRead])
async def admin_list_vendors(
    status_filter: VendorStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[VendorRead]:
    return await service.admin_list_vendors(db, status_filter)


@admin_router.patch("/{vendor_id}", response_model=VendorRead)
async def admin_update_vendor(
    vendor_id: uuid.UUID, payload: VendorAdminUpdate, db: AsyncSession = Depends(get_db)
) -> VendorRead:
    return await service.admin_update_vendor(db, vendor_id, payload)
