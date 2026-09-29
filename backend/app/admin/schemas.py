"""Admin dashboard schemas: platform-wide statistics."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.couriers.schemas import CourierDetailRead
from app.orders.models import DeliveryType, OrderStatus, PaymentMethod
from app.pickup_points.schemas import PickupPointRead


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


class RouteRead(BaseModel):
    coordinates: list[list[float]]
    distance_km: float
    duration_min: int


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
    # Carte : départ (boutique), arrivée (domicile ou point de retrait) et
    # position du livreur si elle est récente (partagée en direct pendant une course).
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    courier_latitude: float | None = None
    courier_longitude: float | None = None
    courier_position_at: datetime | None = None
    courier_live: bool = False
    # Trajet routier (seulement si demandé : ?with_routes=true), voir app/routing.
    route: RouteRead | None = None


class DeliveryMonitorRead(BaseModel):
    generated_at: datetime
    # Début de la journée (UTC = heure de Conakry) pris pour « livrées aujourd'hui ».
    since: datetime
    entries: list[DeliveryMonitorEntry]


class AdminAttention(BaseModel):
    """Ce qui attend une action de l'administration (pastilles du menu et
    section « À traiter » du tableau de bord)."""

    pending_vendors: int
    pending_couriers: int
    pending_applications: int
    pending_reports: int
    pending_withdrawals: int
    pending_orders: int
    unassigned_deliveries: int
    failed_refunds: int


# --- Fiches détaillées (admin) --------------------------------------------------


class ProfileOrder(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    total: int
    item_count: int
    created_at: datetime


class ProfileDelivery(BaseModel):
    sub_order_id: uuid.UUID
    order_id: uuid.UUID
    shop_name: str
    status: OrderStatus
    delivery_type: DeliveryType
    delivery_fee: int
    updated_at: datetime


class ProfileWallet(BaseModel):
    available: int
    pending: int
    total: int


class ProfileAddress(BaseModel):
    label: str
    zone: str
    delivery_type: DeliveryType
    is_default: bool


class ProfileVendorLink(BaseModel):
    id: uuid.UUID
    shop_name: str
    status: str
    zone: str | None


class ProfileCourierLink(BaseModel):
    id: uuid.UUID
    status: str
    vehicle_type: str
    is_online: bool


class ProfileManagedPoint(BaseModel):
    manager_id: uuid.UUID
    pickup_point_id: uuid.UUID
    name: str


class AdminUserProfile(BaseModel):
    id: uuid.UUID
    phone: str
    first_name: str | None
    last_name: str | None
    email: str | None
    email_verified: bool
    role: str
    is_active: bool
    created_at: datetime
    orders_count: int
    orders_total: int
    last_order_at: datetime | None
    addresses: list[ProfileAddress]
    recent_orders: list[ProfileOrder]
    buyer_wallet: ProfileWallet | None
    vendor: ProfileVendorLink | None
    courier: ProfileCourierLink | None
    managed_point: ProfileManagedPoint | None


class AdminUserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    is_active: bool | None = None


class DeliveryStats(BaseModel):
    delivered: int
    in_progress: int
    cancelled: int
    delivered_30d: int


class AdminCourierProfile(BaseModel):
    courier: CourierDetailRead
    email: str | None
    user_is_active: bool
    created_at: datetime
    stats: DeliveryStats
    wallet: ProfileWallet | None
    recent_deliveries: list[ProfileDelivery]


class ManagerSummary(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    phone: str
    full_name: str | None
    email: str | None
    is_active: bool
    created_at: datetime


class PickupStats(BaseModel):
    expected: int
    in_stock: int
    delivered: int
    delivered_30d: int


class AdminPickupPointProfile(BaseModel):
    point: PickupPointRead
    managers: list[ManagerSummary]
    stats: PickupStats
    wallet: ProfileWallet | None
    recent_parcels: list[ProfileDelivery]


class AdminManagerOverview(ManagerSummary):
    pickup_point_id: uuid.UUID
    pickup_point_name: str
    pickup_point_is_active: bool
    parcels_in_stock: int
    parcels_delivered: int
