"""Payment: one record per Order, tracking money status independently of the
provider that handles it.

Kept as its own table (rather than fields on Order) so a real gateway
(Djomy) has somewhere to store its own transaction reference, without
touching the orders module — see provider.py.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base
from app.orders.models import PaymentMethod


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # Paiement en ligne annulé avant tout traitement vendeur (voir
    # app/orders/service.py::cancel_order) : un remboursement a été demandé
    # via l'API payout Djomy (app/payments/djomy_client.py::create_refund_payout)
    # mais pas encore confirmé — REFUNDED/REFUND_FAILED arrivent par le même
    # webhook que le paiement initial (événements payout.*).
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"
    # Le payout a échoué ou a été rejeté côté Djomy — nécessite une
    # intervention manuelle de l'admin (voir admin/commandes/{id}).
    REFUND_FAILED = "refund_failed"


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payments"

    order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, unique=True
    )
    method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status", values_callable=lambda enum: [e.value for e in enum]),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    # Référence transaction chez le prestataire externe (ex. Djomy) — toujours None pour cash on delivery.
    provider_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Identifiant du payout de remboursement chez Djomy (payoutItems[0].itemId
    # de la réponse POST /v1/payout-orders) — distinct de provider_reference
    # (le paiement initial) puisque les deux peuvent coexister le temps du
    # remboursement. Sert à retrouver ce Payment quand le webhook payout.*
    # arrive (data.payout.payoutId).
    refund_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PaymentSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Réglages globaux du module paiement — une seule ligne en base (voir
    repository.get_settings), sur le même principe qu'un singleton plutôt
    qu'une vraie table de configuration multi-valeurs, puisqu'il n'y a pour
    l'instant que quelques réglages."""

    __tablename__ = "payment_settings"

    # Délai de remboursement affiché à l'acheteur quand un paiement en ligne
    # est annulé avant traitement (voir app/orders/service.py::cancel_order) —
    # informatif seulement, Djomy ne garantit pas ce délai, c'est une
    # estimation que l'admin ajuste selon son expérience du prestataire.
    refund_delay_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48)

    # --- Répartition des gains (voir app/wallets/service.py::settle_sub_order) ---
    # Part des frais de livraison reversée au livreur ; Ndjouri garde le reste.
    courier_delivery_share_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    # Rémunération fixe d'un point de retrait par colis remis, prise sur la part Ndjouri.
    pickup_point_fee_per_parcel: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    # Délai entre la livraison et le moment où le gain devient retirable (litiges, retours).
    earnings_hold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # --- Retraits (voir app/wallets/service.py::request_withdrawal) ---
    # Frais estimés à la charge du bénéficiaire, déduits du montant retiré.
    withdrawal_fee_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    min_withdrawal_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
