"""Order schemas: checkout request and the buyer/vendor-facing read models."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.couriers.models import VehicleType
from app.orders.models import DeliveryType, OrderStatus, PaymentMethod
from app.payments.models import PaymentStatus


class DeliveryQuoteRequest(BaseModel):
    """Où livrer — le strict nécessaire pour chiffrer les frais de livraison.
    Base de CheckoutRequest : le devis affiché à l'acheteur et le checkout
    calculent ainsi leurs frais exactement de la même façon."""

    delivery_type: DeliveryType = DeliveryType.HOME_DELIVERY
    # Requis quand delivery_type == PICKUP_POINT (validé dans
    # service._resolve_destination) — route la commande vers le bon
    # gestionnaire de point, en plus du texte figé delivery_address.
    pickup_point_id: uuid.UUID | None = None
    # Position GPS de l'adresse de livraison à domicile (ignorée pour un point
    # de retrait, dont la position est celle du point). Optionnelle : sans
    # elle, le palier de repli s'applique (voir delivery.service.compute_fee).
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class DeliveryQuoteVendorRead(BaseModel):
    vendor_id: uuid.UUID
    shop_name: str
    delivery_fee: int
    # Même calcul que celui figé au checkout (voir SubOrder.estimated_delivery_min) :
    # l'acheteur voit ainsi le même délai avant et après avoir confirmé.
    estimated_delivery_min: date
    estimated_delivery_max: date


class DeliveryQuoteRead(BaseModel):
    vendors: list[DeliveryQuoteVendorRead]
    items_total: int
    delivery_total: int
    total: int


class CheckoutRequest(DeliveryQuoteRequest):
    delivery_address: str = Field(min_length=3, max_length=300)
    # Champs structurés, optionnels : mêmes informations que delivery_address
    # mais gardées séparées pour un affichage ligne par ligne. recipient_*
    # est ignoré (forcé à None) côté service pour un point de retrait — voir
    # service.checkout_cart.
    delivery_zone: str | None = Field(default=None, max_length=300)
    delivery_instructions: str | None = Field(default=None, max_length=300)
    recipient_name: str | None = Field(default=None, max_length=150)
    recipient_phone: str | None = Field(default=None, max_length=20)
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY
    # Numéro mobile money/carte qui paie — pertinent seulement pour ONLINE.
    # Absent : retombe sur le téléphone du compte acheteur (voir
    # service.checkout_cart) — le payeur mobile money n'est pas forcément
    # l'acheteur lui-même, d'où ce champ séparé plutôt que réutiliser User.phone.
    payer_phone: str | None = Field(default=None, max_length=20)


class SubOrderStatusUpdate(BaseModel):
    status: OrderStatus


class StorageLocationUpdate(BaseModel):
    # None efface l'emplacement (colis déjà remis, ou note plus valable).
    storage_location: str | None = Field(default=None, max_length=100)


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
    variant_id: uuid.UUID | None = None
    variant_label: str | None = None
    product_name: str
    # Pas une colonne order_items (voir OrderItem dans models.py) : regardée en
    # direct sur le produit/la variante au moment de la lecture, comme
    # CartItemRead.product_image (app/cart/service.py::get_cart) — un produit
    # ou une variante supprimé(e) depuis laisse simplement ce champ à None,
    # product_name/unit_price restant la source figée pour le reste de la ligne.
    product_image: str | None = None
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
    delivery_fee: int
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
    # courier_id est une vraie colonne (voir app/orders/models.py::SubOrder) ;
    # le reste est attaché en lecture depuis Courier (voir
    # app/orders/service.py::_attach_courier_info), même motif que
    # courier_name/courier_phone sur VendorSubOrderRead ci-dessous — mais
    # jamais le téléphone ici : un acheteur n'a pas besoin de contacter son
    # livreur directement, contrairement au vendeur qui coordonne l'enlèvement.
    courier_id: uuid.UUID | None = None
    courier_name: str | None = None
    courier_status: str | None = None
    courier_average_rating: float | None = None
    courier_review_count: int = 0


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
    storage_location: str | None = None


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
    # pickup_point_id est une vraie colonne (voir app/orders/models.py::Order) ;
    # le nom/la note sont attachés en lecture depuis PickupPoint, même motif
    # que pickup_point_contacts (voir app/orders/service.py::_attach_pickup_point_contacts).
    pickup_point_id: uuid.UUID | None = None
    pickup_point_name: str | None = None
    pickup_point_average_rating: float | None = None
    pickup_point_review_count: int = 0
    payment_method: PaymentMethod
    payment_status: PaymentStatus | None = None
    # Rempli uniquement sur la réponse de POST /orders/checkout quand le
    # paiement est en ligne (voir service.checkout_cart) — jamais persisté,
    # jamais réaffiché sur un GET /orders/{id} ultérieur : un lien Djomy déjà
    # utilisé ou expiré n'a plus de sens à representer.
    payment_redirect_url: str | None = None
    # Rempli quand payment_status == "refund_pending" — délai estimé
    # (réglage admin, voir app/payments/router.py::admin_router) affiché à
    # l'acheteur après une annulation avec remboursement en cours.
    refund_delay_hours: int | None = None
    total: int
    created_at: datetime
    sub_orders: list[SubOrderRead]


class AdminSubOrderRead(SubOrderBase):
    """Sub-order shape for the admin's own order detail view — adds the
    vendor's own account info (not just the frozen shop_name) and the
    assigned courier's info, everything an admin needs to investigate an
    order without switching screens."""

    courier_name: str | None = None
    courier_phone: str | None = None
    storage_location: str | None = None
    # Compte du vendeur propriétaire de cette boutique, attaché en lecture
    # (voir app/admin/repository.py::get_vendor_owner) — shop_name reste la
    # source figée pour l'affichage principal, ces champs ne servent qu'à
    # l'onglet "Boutique" de l'admin.
    vendor_owner_phone: str | None = None
    vendor_owner_email: str | None = None
    vendor_owner_full_name: str | None = None


class AdminOrderRead(BaseModel):
    """Full order detail for the admin's own order screen — order info +
    buyer account + per-sub-order vendor/courier info, organized as tabs on
    the frontend (see pages/admin/commandes/[id].vue)."""

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
    sub_orders: list[AdminSubOrderRead]
    # Acheteur — Order.user_id n'a pas de relation SQLAlchemy vers User
    # (jamais eu besoin ailleurs), attaché en lecture comme le reste ici.
    buyer_phone: str
    buyer_email: str | None = None
    buyer_full_name: str | None = None
