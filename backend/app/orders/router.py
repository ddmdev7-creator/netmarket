"""Order endpoints: checkout, buyer tracking/cancellation, vendor sub-order management.

Route order matters here: the static "/sub-orders" paths are registered
before the dynamic "/{order_id}" path so they aren't swallowed by it.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.orders import service
from app.orders.schemas import (
    CheckoutRequest,
    CourierAssignRequest,
    CourierSubOrderRead,
    DeliveryConfirmRequest,
    DispatchRequest,
    OrderRead,
    PickupPointManagerSubOrderRead,
    SubOrderStatusUpdate,
    VendorSubOrderRead,
)
from app.users.models import User, UserRole

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/checkout", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    return await service.checkout_cart(db, current_user, payload)


@router.get("", response_model=list[OrderRead])
async def list_my_orders(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[OrderRead]:
    return await service.list_my_orders(db, current_user)


@router.get(
    "/sub-orders",
    response_model=list[VendorSubOrderRead],
    dependencies=[Depends(require_role(UserRole.VENDOR))],
)
async def list_my_sub_orders(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[VendorSubOrderRead]:
    return await service.list_my_sub_orders(db, current_user)


@router.get(
    "/courier-deliveries",
    response_model=list[CourierSubOrderRead],
    dependencies=[Depends(require_role(UserRole.COURIER))],
)
async def list_my_deliveries(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[CourierSubOrderRead]:
    return await service.list_my_deliveries(db, current_user)


@router.get(
    "/pickup-point-deliveries",
    response_model=list[PickupPointManagerSubOrderRead],
    dependencies=[Depends(require_role(UserRole.PICKUP_POINT_MANAGER))],
)
async def list_my_point_deliveries(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PickupPointManagerSubOrderRead]:
    return await service.list_my_point_deliveries(db, current_user)


@router.post(
    "/sub-orders/confirm-delivery",
    response_model=VendorSubOrderRead,
    dependencies=[Depends(require_role(UserRole.VENDOR, UserRole.COURIER, UserRole.PICKUP_POINT_MANAGER))],
)
async def confirm_delivery(
    payload: DeliveryConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VendorSubOrderRead:
    return await service.confirm_delivery_by_token(db, current_user, payload.token)


@router.patch(
    "/sub-orders/{sub_order_id}/status",
    response_model=VendorSubOrderRead,
    dependencies=[Depends(require_role(UserRole.VENDOR, UserRole.COURIER, UserRole.PICKUP_POINT_MANAGER))],
)
async def update_sub_order_status(
    sub_order_id: uuid.UUID,
    payload: SubOrderStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VendorSubOrderRead:
    return await service.update_sub_order_status(db, current_user, sub_order_id, payload)


@router.patch(
    "/sub-orders/{sub_order_id}/courier",
    response_model=VendorSubOrderRead,
    dependencies=[Depends(require_role(UserRole.VENDOR))],
)
async def assign_courier(
    sub_order_id: uuid.UUID,
    payload: CourierAssignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VendorSubOrderRead:
    return await service.assign_courier(db, current_user, sub_order_id, payload)


@router.post(
    "/sub-orders/{sub_order_id}/dispatch",
    response_model=VendorSubOrderRead,
    dependencies=[Depends(require_role(UserRole.VENDOR))],
)
async def start_dispatch(
    sub_order_id: uuid.UUID,
    payload: DispatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VendorSubOrderRead:
    return await service.start_dispatch(db, current_user, sub_order_id, payload)


@router.post(
    "/sub-orders/{sub_order_id}/accept-delivery",
    response_model=VendorSubOrderRead,
    dependencies=[Depends(require_role(UserRole.COURIER))],
)
async def accept_delivery(
    sub_order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VendorSubOrderRead:
    return await service.accept_delivery(db, current_user, sub_order_id)


@router.post(
    "/sub-orders/{sub_order_id}/decline-delivery",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.COURIER))],
)
async def decline_delivery(
    sub_order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.decline_delivery(db, current_user, sub_order_id)


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    return await service.get_order(db, current_user, order_id)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    return await service.cancel_order(db, current_user, order_id)
