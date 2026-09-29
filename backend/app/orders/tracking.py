"""Suivi en direct du livreur pendant qu'un colis est en route.

Le livreur envoie sa position depuis son espace (POST /couriers/me/position,
tant que la page est ouverte et qu'il a un colis « shipped ») ; elle est
poussée aussitôt par WebSocket aux acheteurs de ses colis en route, et
consultable via GET /orders/sub-orders/{id}/tracking (repli si la connexion
temps réel est coupée). Jamais exposée hors de ce créneau : ni avant
l'expédition, ni après la remise.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.geo import haversine_km
from app.core.exceptions import NotFoundError
from app.couriers import repository as courier_repository
from app.couriers.models import Courier
from app.notifications.ws_manager import manager as ws_manager
from app.orders import repository
from app.orders.models import DeliveryType, Order, OrderStatus, SubOrder
from app.pickup_points.models import PickupPoint
from app.routing import service as routing_service
from app.users.models import User, UserRole
from app.vendors.models import Vendor

logger = logging.getLogger(__name__)

# Au-delà, la position est jugée trop ancienne pour être montrée comme « en direct ».
POSITION_MAX_AGE = timedelta(minutes=15)
# Vitesse moyenne retenue pour l'estimation d'arrivée (deux-roues en ville).
AVERAGE_SPEED_KMH = 18


def eta_minutes(distance_km: float) -> int:
    return max(2, round(distance_km / AVERAGE_SPEED_KMH * 60))


async def update_position(db: AsyncSession, user: User, latitude: float, longitude: float) -> int:
    """Enregistre la position du livreur et la pousse aux acheteurs de ses
    colis en route. Renvoie le nombre de colis suivis."""
    courier = await courier_repository.get_by_user_id(db, user.id)
    if courier is None:
        raise NotFoundError("Vous n'avez pas de profil livreur.")
    now = datetime.now(UTC)
    courier.latitude = latitude
    courier.longitude = longitude
    courier.position_updated_at = now

    admin_ids = (await db.execute(select(User.id).where(User.role == UserRole.ADMIN, User.is_active.is_(True)))).scalars().all()
    rows = (
        await db.execute(
            select(SubOrder.id, Order.user_id, Order.id)
            .join(Order, SubOrder.order_id == Order.id)
            .where(SubOrder.courier_id == courier.id, SubOrder.status == OrderStatus.SHIPPED)
        )
    ).all()
    await db.commit()

    for sub_order_id, buyer_id, order_id in rows:
        payload = {
            "type": "courier_position",
            "sub_order_id": str(sub_order_id),
            "order_id": str(order_id),
            "latitude": latitude,
            "longitude": longitude,
            "at": now.isoformat(),
        }
        # L'acheteur du colis, et les administrateurs (carte du suivi des livraisons).
        for recipient in (buyer_id, *admin_ids):
            try:
                await ws_manager.send_to_user(recipient, payload)
            except Exception:  # noqa: BLE001 - la relecture périodique rattrape un envoi perdu
                logger.info("Position non poussée pour la sous-commande %s", sub_order_id, exc_info=True)
    return len(rows)


async def get_tracking(db: AsyncSession, user: User, sub_order_id: uuid.UUID) -> dict:
    sub_order = await repository.get_sub_order_by_id(db, sub_order_id)
    if sub_order is None or (sub_order.order.user_id != user.id and user.role != UserRole.ADMIN):
        raise NotFoundError("Colis introuvable.")
    order = sub_order.order

    vendor = await db.get(Vendor, sub_order.vendor_id)
    origin = (vendor.latitude, vendor.longitude) if vendor else (None, None)
    if order.delivery_type == DeliveryType.PICKUP_POINT and order.pickup_point_id is not None:
        point = await db.get(PickupPoint, order.pickup_point_id)
        destination = (point.latitude, point.longitude) if point else (None, None)
    else:
        destination = (order.delivery_latitude, order.delivery_longitude)

    courier: Courier | None = None
    live = False
    if sub_order.status == OrderStatus.SHIPPED and sub_order.courier_id is not None:
        courier = await courier_repository.get_by_id(db, sub_order.courier_id)
        live = bool(
            courier
            and courier.position_updated_at
            and courier.latitude is not None
            and datetime.now(UTC) - courier.position_updated_at <= POSITION_MAX_AGE
        )

    distance = None
    if live and None not in destination:
        distance = round(haversine_km(courier.latitude, courier.longitude, *destination), 1)

    # Trajet routier : du livreur à la destination pendant la course, sinon
    # de la boutique à la destination (aperçu avant l'expédition).
    route = None
    if sub_order.status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED) and None not in destination:
        start = (courier.latitude, courier.longitude) if live else origin
        if None not in start:
            route = await routing_service.get_route([start, destination])
    if route and live:
        distance = route["distance_km"]
    eta = route["duration_min"] if route and live else (eta_minutes(distance) if distance is not None else None)
    return {
        "sub_order_id": sub_order.id,
        "status": sub_order.status,
        "delivery_type": order.delivery_type,
        "origin_latitude": origin[0],
        "origin_longitude": origin[1],
        "destination_latitude": destination[0],
        "destination_longitude": destination[1],
        "courier_latitude": courier.latitude if live else None,
        "courier_longitude": courier.longitude if live else None,
        "courier_position_at": courier.position_updated_at if live else None,
        "distance_km": distance,
        "eta_minutes": eta,
        "route": route,
    }
