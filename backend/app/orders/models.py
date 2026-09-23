"""Order, SubOrder and OrderItem ORM models.

Order != SubOrder: a buyer's cart can span several vendors, so checkout
splits it into one SubOrder per vendor, each with its own status and
commission, while Order carries the buyer-facing totals and delivery info.
"""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import ARRAY, CheckConstraint, Date, Enum as SAEnum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    SHIPPED = "shipped"
    # Point de retrait uniquement : le livreur a déposé le colis, en attente
    # que le gestionnaire du point le remette à l'acheteur (voir
    # app/orders/service.py::_allowed_next_statuses). Inatteignable pour une
    # livraison à domicile, qui va toujours directement SHIPPED → DELIVERED.
    ARRIVED_AT_PICKUP_POINT = "arrived_at_pickup_point"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    CASH_ON_DELIVERY = "cash_on_delivery"
    # Paiement en ligne (mobile money, carte...) via Djomy — voir
    # app/payments/provider.py::DjomyProvider. Une seule valeur générique
    # plutôt que "djomy" : le moyen réel (OM/MOMO/carte...) est choisi par
    # l'acheteur sur le portail de paiement, pas figé côté commande.
    ONLINE = "online"
    # Solde NdjouriBank de l'acheteur (app/wallets/buyer_service.py) : débité
    # au checkout, le paiement est confirmé immédiatement.
    WALLET = "wallet"


class DeliveryType(StrEnum):
    # Les deux partagent le même champ delivery_address en texte libre — un
    # point de retrait n'est pas (encore) une entité structurée gérée par la
    # plateforme (annuaire de points façon Wildberries), juste une indication
    # de comment lire cette adresse. Voir cahier des charges §7.2.
    HOME_DELIVERY = "home_delivery"
    PICKUP_POINT = "pickup_point"


def _status_column():
    # Same Postgres enum type ("order_status") reused for Order and SubOrder:
    # they share one status vocabulary by design.
    return mapped_column(
        SAEnum(OrderStatus, name="order_status", values_callable=lambda enum: [e.value for e in enum]),
        default=OrderStatus.PENDING,
        nullable=False,
    )


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),)

    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[OrderStatus] = _status_column()
    # Zone/quartier + point de repère textuel plutôt qu'adresse formelle.
    delivery_address: Mapped[str] = mapped_column(String(300), nullable=False)
    # Champs structurés, figés au checkout comme delivery_address — permettent
    # un affichage ligne par ligne (zone / instructions / destinataire) côté
    # frontend sans reparser le texte combiné. Nullable : les commandes
    # passées avant leur ajout retombent sur delivery_address en affichage.
    delivery_zone: Mapped[str | None] = mapped_column(String(300), nullable=True)
    delivery_instructions: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Uniquement pour une livraison à domicile — jamais renseigné pour un
    # point de retrait, dont le contact affiché est le gestionnaire du point
    # (voir app/orders/service.py::_attach_pickup_point_contacts, en direct
    # plutôt que figé puisque les gestionnaires peuvent changer après coup).
    recipient_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_type: Mapped[DeliveryType] = mapped_column(
        SAEnum(DeliveryType, name="delivery_type", values_callable=lambda enum: [e.value for e in enum]),
        default=DeliveryType.HOME_DELIVERY,
        nullable=False,
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method", values_callable=lambda enum: [e.value for e in enum]),
        default=PaymentMethod.CASH_ON_DELIVERY,
        nullable=False,
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    # Quel point précis (annuaire admin) — seulement renseigné quand
    # delivery_type == PICKUP_POINT. Additif par rapport à delivery_address
    # (texte figé, toujours la source d'affichage) : sert uniquement à router
    # la commande vers le bon gestionnaire de point (voir
    # app/orders/service.py::list_my_point_deliveries).
    pickup_point_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pickup_points.id"), nullable=True
    )
    # Position GPS de destination, figée au checkout (voir
    # app/orders/service.py::_resolve_destination) : celle soumise par
    # l'acheteur pour un domicile, celle du point pour un point de retrait.
    # Nullable : domicile sans position, et commandes passées avant l'ajout
    # de ces colonnes (elles ne servaient alors qu'au calcul des frais).
    delivery_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    sub_orders: Mapped[list["SubOrder"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class SubOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sub_orders"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_sub_orders_amount_non_negative"),
        CheckConstraint("commission >= 0", name="ck_sub_orders_commission_non_negative"),
        CheckConstraint("delivery_fee >= 0", name="ck_sub_orders_delivery_fee_non_negative"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)
    # Livreur assigné par le vendeur (voir app/orders/service.py::assign_courier).
    # Nullable tant que le colis n'est pas encore en préparation/expédié — mais
    # obligatoire pour passer au statut "shipped" (voir
    # app/orders/service.py::update_sub_order_status), un colis ne pouvant pas
    # être "en route" sans personne pour le transporter.
    courier_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("couriers.id"), nullable=True
    )
    status: Mapped[OrderStatus] = _status_column()
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # Commission due à la marketplace, calculée depuis Vendor.commission_rate au moment de la commande.
    commission: Mapped[int] = mapped_column(Integer, nullable=False)
    # Frais de livraison de ce colis, calculés puis figés au checkout d'après la
    # grille de paliers de distance (voir app/delivery/service.py::compute_fee).
    # Distinct de amount : la commission ne s'applique qu'aux articles, jamais
    # au frais de livraison, et Order.total = Σ(amount + delivery_fee).
    delivery_fee: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # Nom de la boutique figé au moment de la commande (affichage stable même si la boutique est renommée).
    shop_name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Estimation de livraison calculée et figée au checkout (voir
    # app/common/delivery_estimate.py et service.checkout_cart) — délai de
    # préparation du vendeur + heuristique de zone (même zone acheteur/vendeur
    # ou non). Figée plutôt que recalculée à la volée pour que l'estimation
    # affichée à l'acheteur ne bouge pas si le vendeur modifie son délai de
    # préparation après coup. Nullable : les commandes passées avant l'ajout
    # de cette fonctionnalité n'ont simplement rien à afficher.
    estimated_delivery_min: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_delivery_max: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Dispatch en cours (voir app/orders/service.py::start_dispatch) : le
    # livreur qui a l'offre active en ce moment, et la file des suivants par
    # distance croissante à essayer s'il refuse/n'a pas répondu à temps.
    # Les deux sont vidés dès qu'un livreur accepte (courier_id posé) ou que
    # la file s'épuise sans succès — ils ne reflètent donc qu'un dispatch
    # EN COURS, jamais un historique.
    dispatch_offered_courier_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("couriers.id"), nullable=True
    )
    dispatch_queue: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), default=list, nullable=False)

    # Emplacement de stockage au point de retrait (ex. "Étagère B3") — texte
    # libre renseigné/modifié par le gestionnaire du point (voir
    # app/orders/service.py::update_storage_location), pour retrouver
    # rapidement le colis physique au moment de la remise. Sans objet pour
    # une livraison à domicile (delivery_type == home_delivery).
    storage_location: Mapped[str | None] = mapped_column(String(100), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="sub_orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="sub_order", cascade="all, delete-orphan")


class OrderItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
    )

    sub_order_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sub_orders.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    # Nom du produit figé au moment de la commande (affichage stable si le produit est renommé/retiré).
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Prix unitaire figé au moment de la commande (le prix produit peut changer ensuite).
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    # SET NULL (pas CASCADE, contrairement à cart_items.variant_id) : une
    # commande passée doit rester consultable même après suppression de la
    # variante achetée — d'où variant_label ci-dessous, figé comme
    # product_name/unit_price, seule source d'affichage une fois variant_id
    # devenu None.
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    variant_label: Mapped[str | None] = mapped_column(String(300), nullable=True)

    sub_order: Mapped["SubOrder"] = relationship(back_populates="items")
