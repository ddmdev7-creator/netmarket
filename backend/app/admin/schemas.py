"""Admin dashboard schemas: platform-wide statistics."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.orders.models import DeliveryType, OrderStatus


class TopProduct(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity_sold: int


class TopVendor(BaseModel):
    vendor_id: uuid.UUID
    shop_name: str
    revenue: int


class AdminStats(BaseModel):
    total_vendors: int
    pending_vendors: int
    approved_vendors: int
    total_products: int
    total_orders: int
    orders_by_status: dict[str, int]
    # Ventes/commission comptées sur les sous-commandes livrées uniquement :
    # en paiement à la livraison, l'argent ne change vraiment de main qu'à ce moment-là.
    total_sales: int
    total_commission: int
    top_products: list[TopProduct]
    top_vendors: list[TopVendor]


class ActiveDeliveryRead(BaseModel):
    """Un colis en cours d'acheminement, pour la carte admin des livreurs.
    Le nom des livreurs n'est pas répété ici : l'écran charge déjà la liste
    complète (/admin/couriers) et fait la correspondance par id."""

    sub_order_id: uuid.UUID
    order_id: uuid.UUID
    status: OrderStatus
    vendor_id: uuid.UUID
    shop_name: str
    created_at: datetime
    origin_latitude: float | None
    origin_longitude: float | None
    delivery_type: DeliveryType
    delivery_zone: str | None
    delivery_address: str
    pickup_point_name: str | None
    destination_latitude: float | None
    destination_longitude: float | None
    courier_id: uuid.UUID | None
    dispatch_offered_courier_id: uuid.UUID | None
