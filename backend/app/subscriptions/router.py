"""Vendor subscription plans, subscribing, and admin confirmation.

No online payment gateway is wired up yet (see app/payments/provider.py),
so /subscribe only records the request — an admin confirms it manually once
the vendor has paid off-platform, mirroring how vendor onboarding itself is
validated (see app/vendors/router.py's admin_router).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.subscriptions import service
from app.subscriptions.models import SubscriptionStatus
from app.subscriptions.schemas import SubscribeRequest, SubscriptionPlanRead, VendorSubscriptionRead
from app.users.models import User, UserRole
from app.vendors import service as vendors_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
admin_router = APIRouter(
    prefix="/admin/subscriptions", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.get("/plans", response_model=list[SubscriptionPlanRead])
async def list_plans(db: AsyncSession = Depends(get_db)) -> list[SubscriptionPlanRead]:
    return await service.list_plans(db)


@router.post("/subscribe", response_model=VendorSubscriptionRead)
async def subscribe(
    payload: SubscribeRequest,
    current_user: User = Depends(require_role(UserRole.VENDOR)),
    db: AsyncSession = Depends(get_db),
) -> VendorSubscriptionRead:
    vendor = await vendors_service.get_my_vendor(db, current_user)
    return await service.subscribe(db, vendor, payload.plan_id)


@router.get("/me", response_model=VendorSubscriptionRead | None)
async def get_my_subscription(
    current_user: User = Depends(require_role(UserRole.VENDOR)),
    db: AsyncSession = Depends(get_db),
) -> VendorSubscriptionRead | None:
    vendor = await vendors_service.get_my_vendor(db, current_user)
    return await service.get_my_subscription(db, vendor)


@admin_router.get("", response_model=list[VendorSubscriptionRead])
async def admin_list_subscriptions(
    status_filter: SubscriptionStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[VendorSubscriptionRead]:
    return await service.list_by_status(db, status_filter)


@admin_router.post("/{subscription_id}/confirm", response_model=VendorSubscriptionRead)
async def admin_confirm_subscription(
    subscription_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> VendorSubscriptionRead:
    return await service.admin_confirm(db, subscription_id)


@admin_router.post("/{subscription_id}/cancel", response_model=VendorSubscriptionRead)
async def admin_cancel_subscription(
    subscription_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> VendorSubscriptionRead:
    return await service.admin_cancel(db, subscription_id)
