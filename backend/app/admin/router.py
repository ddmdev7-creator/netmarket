"""Admin dashboard: platform-wide statistics and global order visibility.

Vendor validation lives in app/vendors/router.py (admin_router, under
/admin/vendors) since it's vendor-specific business logic; this module covers
the cross-cutting concerns (stats, global order list).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import profiles, service
from app.admin.schemas import (
    ActiveDeliveryRead,
    AdminAttention,
    AdminCourierProfile,
    AdminManagerOverview,
    AdminPickupPointProfile,
    AdminStats,
    AdminUserProfile,
    AdminUserUpdate,
    DeliveryMonitorRead,
)
from app.core.deps import get_current_user, get_db, require_role
from app.core.pagination import Page, PageParams, pagination_params
from app.orders.models import OrderStatus
from app.orders.schemas import AdminOrderRead, OrderRead
from app.users.models import User, UserRole

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.get("/users/{user_id}/profile", response_model=AdminUserProfile)
async def get_user_profile(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminUserProfile:
    """Fiche complète d'un utilisateur : compte, commandes, adresses, rôles liés."""
    return await profiles.user_profile(db, user_id)


@router.patch("/users/{user_id}", response_model=AdminUserProfile)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminUserProfile:
    """Corriger le nom ou l'email, activer ou désactiver un compte."""
    return await profiles.update_user(db, current_user, user_id, payload)


@router.get("/couriers/{courier_id}/profile", response_model=AdminCourierProfile)
async def get_courier_profile(courier_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminCourierProfile:
    return await profiles.courier_profile(db, courier_id)


@router.get("/pickup-points/{point_id}/profile", response_model=AdminPickupPointProfile)
async def get_pickup_point_profile(point_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminPickupPointProfile:
    return await profiles.pickup_point_profile(db, point_id)


@router.get("/pickup-point-managers/overview", response_model=list[AdminManagerOverview])
async def get_managers_overview(db: AsyncSession = Depends(get_db)) -> list[AdminManagerOverview]:
    """Tous les gestionnaires de point, avec leur point et leur activité."""
    return await profiles.managers_overview(db)


@router.get("/attention", response_model=AdminAttention)
async def get_attention(db: AsyncSession = Depends(get_db)) -> AdminAttention:
    """Compteurs de ce qui attend une action (menu et tableau de bord)."""
    return await service.get_attention(db)


@router.get("/stats", response_model=AdminStats)
async def get_stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    return await service.get_stats(db)


@router.get("/deliveries/active", response_model=list[ActiveDeliveryRead])
async def list_active_deliveries(db: AsyncSession = Depends(get_db)) -> list[ActiveDeliveryRead]:
    return await service.list_active_deliveries(db)


@router.get("/deliveries/monitor", response_model=DeliveryMonitorRead)
async def get_delivery_monitor(
    with_routes: bool = Query(default=False, description="Ajouter le trajet routier de chaque livraison en cours"),
    db: AsyncSession = Depends(get_db),
) -> DeliveryMonitorRead:
    """Écran de suivi des livraisons, rafraîchi en continu par le front."""
    return await service.get_delivery_monitor(db, with_routes=with_routes)


@router.get("/orders", response_model=Page[OrderRead])
async def list_orders(
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    params: PageParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
) -> Page[OrderRead]:
    items, total = await service.list_orders(db, params, status_filter)
    return Page.create(items=items, total=total, params=params)


@router.get("/orders/{order_id}", response_model=AdminOrderRead)
async def get_order_detail(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminOrderRead:
    return await service.get_order_detail(db, order_id)
