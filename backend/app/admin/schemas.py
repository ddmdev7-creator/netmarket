"""Admin dashboard schemas: platform-wide statistics."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.orders.models import DeliveryType, OrderStatus, PaymentMethod


class TopProduct(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity_sold: int


class TopVendor(BaseModel):
    vendor_id: uuid.UUID
    shop_name: str
    revenue: int


class DailyActivity(BaseModel):
    date: date
    orders: int
    # Montant des commandes passées ce jour-là (hors annulées).
    order_amount: int
    signups: int


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
    # Graphiques du tableau de bord : 30 derniers jours, jour par jour (jours
    # sans activité inclus, à zéro), et répartitions.
    daily_activity: list[DailyActivity]
    orders_by_payment_method: dict[str, int]
    users_by_role: dict[str, int]


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


class DeliveryMonitorEntry(BaseModel):
    """Une sous-commande suivie par l'écran admin de suivi des livraisons
    (pages/admin/livraisons) — tout ce qu'il faut pour repérer un colis
    bloqué sans ouvrir la commande."""

    sub_order_id: uuid.UUID
    order_id: uuid.UUID
    status: OrderStatus
    created_at: datetime
    # Dernier changement de la sous-commande — en pratique son dernier
    # changement de statut/livreur, d'où l'« immobile depuis » de l'écran.
    updated_at: datetime
    estimated_delivery_min: date | None
    estimated_delivery_max: date | None
    amount: int
    delivery_fee: int
    payment_method: PaymentMethod
    vendor_id: uuid.UUID
    shop_name: str
    vendor_zone: str | None
    delivery_type: DeliveryType
    delivery_zone: str | None
    delivery_address: str
    pickup_point_name: str | None
    storage_location: str | None
    buyer_name: str | None
    buyer_phone: str | None
    courier_id: uuid.UUID | None
    courier_name: str | None
    courier_phone: str | None
    courier_is_online: bool | None
    dispatch_offered_courier_id: uuid.UUID | None
    dispatch_offered_courier_name: str | None


class DeliveryMonitorRead(BaseModel):
    generated_at: datetime
    # Début de la journée (UTC = heure de Conakry) pris pour « livrées aujourd'hui ».
    since: datetime
    entries: list[DeliveryMonitorEntry]
