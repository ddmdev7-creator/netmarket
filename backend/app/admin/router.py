"""Admin dashboard: platform-wide statistics and global order visibility.

Vendor validation lives in app/vendors/router.py (admin_router, under
/admin/vendors) since it's vendor-specific business logic; this module covers
the cross-cutting concerns (stats, global order list).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.schemas import ActiveDeliveryRead, AdminStats, DeliveryMonitorRead
from app.core.deps import get_db, require_role
from app.core.pagination import Page, PageParams, pagination_params
from app.orders.models import OrderStatus
from app.orders.schemas import AdminOrderRead, OrderRead
from app.users.models import UserRole

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.get("/stats", response_model=AdminStats)
async def get_stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    return await service.get_stats(db)


@router.get("/deliveries/active", response_model=list[ActiveDeliveryRead])
async def list_active_deliveries(db: AsyncSession = Depends(get_db)) -> list[ActiveDeliveryRead]:
    return await service.list_active_deliveries(db)


@router.get("/deliveries/monitor", response_model=DeliveryMonitorRead)
async def get_delivery_monitor(db: AsyncSession = Depends(get_db)) -> DeliveryMonitorRead:
    """Écran de suivi des livraisons, rafraîchi en continu par le front."""
    return await service.get_delivery_monitor(db)


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
