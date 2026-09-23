"""Order schemas: checkout request and the buyer/vendor-facing read models."""

import uuid
from datetime import date, datetime
from typing import Literal

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


class OrderCancelRequest(BaseModel):
    # Paiement en ligne : "wallet" rembourse tout de suite sur le solde
    # NdjouriBank (si ouvert) au lieu d'un versement Djomy vers le payeur.
    # Payé avec le solde : toujours remboursé sur le solde.
    refund_to: Literal["original", "wallet"] = "original"


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
    # Montant déjà remboursé sur le solde NdjouriBank de l'acheteur
    # (commande ou sous-commandes annulées).
    wallet_refunded_amount: int = 0
    total: int
    created_at: datetime
    sub_orders: list[SubOrderRead]


class AdminVendorInfo(BaseModel):
    """La boutique telle qu'elle est aujourd'hui (SubOrder.shop_name reste le
    nom figé au checkout) + le compte de son propriétaire."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_name: str
    status: str
    zone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    commission_rate: float
    preparation_days: int
    created_at: datetime
    owner_full_name: str | None = None
    owner_phone: str | None = None
    owner_email: str | None = None


class AdminCourierInfo(BaseModel):
    """Le livreur d'une sous-commande. face_photo_key n'est pas une URL
    publique : l'écran admin la charge via GET /couriers/{id}/documents/{key}
    (voir app/couriers/router.py::get_courier_document)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None = None
    phone: str
    status: str
    vehicle_type: VehicleType
    vehicle_name: str | None = None
    vehicle_plate_number: str | None = None
    zone: str | None = None
    is_online: bool
    face_photo_key: str | None = None
    average_rating: float | None = None
    review_count: int = 0


class AdminBuyerInfo(BaseModel):
    id: uuid.UUID
    full_name: str | None = None
    phone: str
    email: str | None = None
    email_verified: bool
    is_active: bool
    created_at: datetime
    order_count: int


class AdminPickupPointInfo(BaseModel):
    """Le point de retrait lu en direct (pas figé sur la commande), comme
    pickup_point_contacts."""

    id: uuid.UUID
    name: str
    zone: str
    latitude: float | None = None
    longitude: float | None = None
    is_active: bool
    vendor_shop_name: str | None = None
    average_rating: float | None = None
    review_count: int = 0


class AdminSubOrderRead(SubOrderBase):
    """Sub-order shape for the admin's own order detail view — adds the
    vendor's current shop + owner account (not just the frozen shop_name)
    and the assigned courier's full profile, everything an admin needs to
    investigate an order without switching screens."""

    created_at: datetime
    updated_at: datetime
    storage_location: str | None = None
    vendor: AdminVendorInfo | None = None
    courier: AdminCourierInfo | None = None
    # Dispatch en cours, pas encore accepté (voir SubOrder.dispatch_offered_courier_id).
    dispatch_offered_courier_name: str | None = None


class AdminOrderRead(BaseModel):
    """Full order detail for the admin's own order screen — order info +
    buyer account + pickup point + per-sub-order vendor/courier info (see
    pages/admin/commandes/[id].vue)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: OrderStatus
    delivery_address: str
    delivery_type: DeliveryType
    delivery_zone: str | None = None
    delivery_instructions: str | None = None
    delivery_latitude: float | None = None
    delivery_longitude: float | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    pickup_point_contacts: list[PickupPointContactRead] = []
    payment_method: PaymentMethod
    payment_status: PaymentStatus | None = None
    total: int
    created_at: datetime
    sub_orders: list[AdminSubOrderRead]
    # Order.user_id n'a pas de relation SQLAlchemy vers User (jamais eu
    # besoin ailleurs), attaché en lecture comme le reste ici. None si le
    # compte a disparu.
    buyer: AdminBuyerInfo | None = None
    pickup_point: AdminPickupPointInfo | None = None
