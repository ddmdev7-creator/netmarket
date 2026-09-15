"""Order schemas: checkout request and the buyer/vendor-facing read models."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.couriers.models import VehicleType
from app.orders.models import DeliveryType, OrderStatus, PaymentMethod
from app.payments.models import PaymentStatus


class CheckoutRequest(BaseModel):
    delivery_address: str = Field(min_length=3, max_length=300)
    delivery_type: DeliveryType = DeliveryType.HOME_DELIVERY
    # Requis quand delivery_type == PICKUP_POINT (validé dans
    # service.checkout_cart) — route la commande vers le bon gestionnaire de
    # point, en plus du texte figé delivery_address.
    pickup_point_id: uuid.UUID | None = None
    # Champs structurés, optionnels : mêmes informations que delivery_address
    # mais gardées séparées pour un affichage ligne par ligne. recipient_*
    # est ignoré (forcé à None) côté service pour un point de retrait — voir
    # service.checkout_cart.
    delivery_zone: str | None = Field(default=None, max_length=300)
    delivery_instructions: str | None = Field(default=None, max_length=300)
    recipient_name: str | None = Field(default=None, max_length=150)
    recipient_phone: str | None = Field(default=None, max_length=20)
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY


class SubOrderStatusUpdate(BaseModel):
    status: OrderStatus


class DeliveryConfirmRequest(BaseModel):
    token: str


class CourierAssignRequest(BaseModel):
    # None désassigne — le vendeur peut toujours livrer lui-même.
    courier_id: uuid.UUID | None = None


class DispatchRequest(BaseModel):
    # Filtre optionnel — voir service.start_dispatch, qui ne retient que les
    # livreurs en ligne de ce type d'engin (moto/taxi/voiture) avant de trier
    # par distance.
    vehicle_type: VehicleType | None = None


class PickupPointContactRead(BaseModel):
    """One staff member of a pickup point, looked up live at read time (not
    frozen on the order) — see app/orders/service.py::_attach_pickup_point_contacts
    for why: managers can be added/reassigned after the order was placed, so
    there's no single "the" manager to freeze at checkout."""

    name: str | None
    phone: str


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: int


class SubOrderBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    shop_name: str
    status: OrderStatus
    amount: int
    commission: int
    items: list[OrderItemRead]
    # None pour les commandes passées avant l'ajout de l'estimation de
    # livraison (voir app/orders/models.py::SubOrder.estimated_delivery_min).
    estimated_delivery_min: date | None = None
    estimated_delivery_max: date | None = None


class SubOrderRead(SubOrderBase):
    """Buyer-facing sub-order, nested under OrderRead.

    delivery_token is the buyer's own private delivery-confirmation code
    (set only while status is "shipped") — it must NOT appear on
    VendorSubOrderRead below: the whole point is that the vendor never sees
    the value, only what their camera reads off the buyer's screen.
    """

    delivery_token: str | None = None


class VendorSubOrderRead(SubOrderBase):
    """Sub-order shape for the vendor's own order list/actions.

    Adds the order-level fields a vendor needs to actually fulfill the
    order (when it came in, where to deliver it) that OrderRead.sub_orders
    omits because the parent Order already carries them for the buyer.
    """

    order_id: uuid.UUID
    created_at: datetime
    delivery_address: str
    delivery_type: DeliveryType
    delivery_zone: str | None = None
    delivery_instructions: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    pickup_point_contacts: list[PickupPointContactRead] = []
    courier_id: uuid.UUID | None = None
    courier_name: str | None = None
    courier_phone: str | None = None
    # Dispatch en cours (voir app/orders/models.py::SubOrder.dispatch_offered_courier_id) —
    # None dès qu'un livreur a accepté (courier_id posé) ou que la recherche
    # s'est arrêtée sans succès.
    dispatch_offered_courier_id: uuid.UUID | None = None
    dispatch_offered_courier_name: str | None = None


class CourierSubOrderRead(BaseModel):
    """Sub-order shape for the assigned courier's own deliveries list — no
    amount/commission (platform/vendor financials aren't the courier's
    business here; cash handling for cash-on-delivery stays an off-platform
    arrangement between vendor and courier for this simple first version)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    shop_name: str
    status: OrderStatus
    items: list[OrderItemRead]
    created_at: datetime
    delivery_address: str
    delivery_type: DeliveryType
    delivery_zone: str | None = None
    delivery_instructions: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    pickup_point_contacts: list[PickupPointContactRead] = []
    # Le propre QR "dépôt" du livreur pour une sous-commande pickup_point
    # expédiée — le gestionnaire du point le scanne pour confirmer la
    # réception (voir _attach_pickup_dropoff_token). None pour une livraison
    # à domicile, ou une fois la sous-commande passée à l'étape suivante.
    pickup_dropoff_token: str | None = None


class PickupPointManagerSubOrderRead(BaseModel):
    """Sub-order shape for the pickup point manager's own list — mirrors
    CourierSubOrderRead, plus who's dropping the parcel off so the manager
    knows who to expect."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    shop_name: str
    status: OrderStatus
    items: list[OrderItemRead]
    created_at: datetime
    delivery_address: str
    delivery_type: DeliveryType
    delivery_zone: str | None = None
    delivery_instructions: str | None = None
    courier_name: str | None = None
    courier_phone: str | None = None


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: OrderStatus
    delivery_address: str
    delivery_type: DeliveryType
    delivery_zone: str | None = None
    delivery_instructions: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    pickup_point_contacts: list[PickupPointContactRead] = []
    payment_method: PaymentMethod
    payment_status: PaymentStatus | None = None
    total: int
    created_at: datetime
    sub_orders: list[SubOrderRead]
