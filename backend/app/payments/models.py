"""Payment: one record per Order, tracking money status independently of the
provider that handles it.

Kept as its own table (rather than fields on Order) so a real gateway
(Djomy) has somewhere to store its own transaction reference, without
touching the orders module — see provider.py.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum as SAEnum, ForeignKey, String
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
