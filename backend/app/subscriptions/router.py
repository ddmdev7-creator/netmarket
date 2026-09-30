"""Vendor subscription plans, subscribing/renewing, trials and admin management.

No online payment gateway is wired up for subscriptions yet (see
app/payments/provider.py), so /subscribe only records the request — an admin
confirms it manually once the vendor has paid off-platform. See
app/subscriptions/service.py for the business rules (no refunds, stacked
renewals, trials) and quotas.py for what each plan unlocks.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.subscriptions import service
from app.subscriptions.models import SubscriptionStatus
from app.subscriptions.schemas import (
    AdminCancelRequest,
    AdminChangePlanRequest,
    AdminExtendRequest,
    AdminSubscriptionRead,
    AdminTrialRequest,
    SubscribeRequest,
    SubscriptionOverview,
    SubscriptionPlanCreate,
    SubscriptionPlanRead,
    SubscriptionPlanUpdate,
    SubscriptionSettingsRead,
    SubscriptionSettingsUpdate,
    VendorSubscriptionRead,
)
from app.users.models import User, UserRole
from app.vendors import service as vendors_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
admin_router = APIRouter(
    prefix="/admin/subscriptions", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)
admin_plans_router = APIRouter(
    prefix="/admin/subscription-plans", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
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


@router.get("/me/overview", response_model=SubscriptionOverview)
async def get_my_overview(
    current_user: User = Depends(require_role(UserRole.VENDOR)),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOverview:
    vendor = await vendors_service.get_my_vendor(db, current_user)
    return await service.overview(db, vendor)


@router.post("/{subscription_id}/cancel", response_model=VendorSubscriptionRead)
async def cancel_my_request(
    subscription_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.VENDOR)),
    db: AsyncSession = Depends(get_db),
) -> VendorSubscriptionRead:
    vendor = await vendors_service.get_my_vendor(db, current_user)
    return await service.vendor_cancel_pending(db, vendor, subscription_id)


# --- Admin : abonnements --------------------------------------------------------


@admin_router.get("", response_model=list[AdminSubscriptionRead])
async def admin_list_subscriptions(
    status_filter: SubscriptionStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[AdminSubscriptionRead]:
    return await service.admin_list(db, status_filter)


@admin_router.get("/settings", response_model=SubscriptionSettingsRead)
async def admin_get_settings(db: AsyncSession = Depends(get_db)) -> SubscriptionSettingsRead:
    return await service.get_settings(db)


@admin_router.patch("/settings", response_model=SubscriptionSettingsRead)
async def admin_update_settings(
    payload: SubscriptionSettingsUpdate, db: AsyncSession = Depends(get_db)
) -> SubscriptionSettingsRead:
    return await service.update_settings(db, payload)


@admin_router.post("/trials", response_model=VendorSubscriptionRead, status_code=status.HTTP_201_CREATED)
async def admin_grant_trial(payload: AdminTrialRequest, db: AsyncSession = Depends(get_db)) -> VendorSubscriptionRead:
    return await service.grant_trial(db, payload.vendor_id, payload.plan_id, payload.days)


@admin_router.get("/vendors/{vendor_id}", response_model=SubscriptionOverview)
async def admin_vendor_overview(vendor_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> SubscriptionOverview:
    return await service.admin_vendor_overview(db, vendor_id)


@admin_router.post("/{subscription_id}/confirm", response_model=VendorSubscriptionRead)
async def admin_confirm_subscription(
    subscription_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> VendorSubscriptionRead:
    return await service.admin_confirm(db, subscription_id)


@admin_router.post("/{subscription_id}/cancel", response_model=VendorSubscriptionRead)
async def admin_cancel_subscription(
    subscription_id: uuid.UUID, payload: AdminCancelRequest | None = None, db: AsyncSession = Depends(get_db)
) -> VendorSubscriptionRead:
    return await service.admin_cancel(db, subscription_id, payload.reason if payload else None)


@admin_router.post("/{subscription_id}/extend", response_model=VendorSubscriptionRead)
async def admin_extend_subscription(
    subscription_id: uuid.UUID, payload: AdminExtendRequest, db: AsyncSession = Depends(get_db)
) -> VendorSubscriptionRead:
    return await service.admin_extend(db, subscription_id, payload.days)


@admin_router.post("/{subscription_id}/change-plan", response_model=VendorSubscriptionRead)
async def admin_change_plan(
    subscription_id: uuid.UUID, payload: AdminChangePlanRequest, db: AsyncSession = Depends(get_db)
) -> VendorSubscriptionRead:
    return await service.admin_change_plan(db, subscription_id, payload.plan_id)


# --- Admin : formules -----------------------------------------------------------


@admin_plans_router.get("", response_model=list[SubscriptionPlanRead])
async def admin_list_plans(db: AsyncSession = Depends(get_db)) -> list[SubscriptionPlanRead]:
    return await service.admin_list_plans(db)


@admin_plans_router.post("", response_model=SubscriptionPlanRead, status_code=status.HTTP_201_CREATED)
async def admin_create_plan(payload: SubscriptionPlanCreate, db: AsyncSession = Depends(get_db)) -> SubscriptionPlanRead:
    return await service.admin_create_plan(db, payload)


@admin_plans_router.patch("/{plan_id}", response_model=SubscriptionPlanRead)
async def admin_update_plan(
    plan_id: uuid.UUID, payload: SubscriptionPlanUpdate, db: AsyncSession = Depends(get_db)
) -> SubscriptionPlanRead:
    return await service.admin_update_plan(db, plan_id, payload)
