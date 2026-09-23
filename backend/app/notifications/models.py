"""In-app notification ORM model: a persisted, per-user feed backing the bell
icon (badge count + history) and pushed live over WebSocket when the
recipient is connected (see app/notifications/ws_manager.py). Separate from
the email side of this module (still in service.py) — a status change or a
new order triggers both channels, but each is independent and best-effort.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class NotificationType(StrEnum):
    ORDER_RECEIVED = "order_received"
    ORDER_STATUS_CHANGED = "order_status_changed"
    COURIER_VERIFICATION_APPROVED = "courier_verification_approved"
    COURIER_VERIFICATION_REJECTED = "courier_verification_rejected"
    DELIVERY_REQUEST = "delivery_request"
    DELIVERY_REQUEST_ACCEPTED = "delivery_request_accepted"
    DELIVERY_NO_COURIER_FOUND = "delivery_no_courier_found"
    # Candidature gestionnaire de point de retrait (app/pickup_point_applications).
    PICKUP_APPLICATION_INVITED = "pickup_application_invited"
    PICKUP_APPLICATION_SUBMITTED = "pickup_application_submitted"
    PICKUP_APPLICATION_APPROVED = "pickup_application_approved"
    PICKUP_APPLICATION_CHANGES_REQUESTED = "pickup_application_changes_requested"
    PICKUP_APPLICATION_REJECTED = "pickup_application_rejected"


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # La commande concernée, pour que le frontend sache où rediriger au clic
    # (/commandes/{order_id} côté acheteur, /vendeur/commandes côté vendeur).
    # ondelete="CASCADE" : pas de notification orpheline pointant vers une
    # commande qui n'existe plus (aucune suppression de commande aujourd'hui,
    # mais on ne veut pas d'un FK bloquant si ça change un jour).
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=True
    )
    # Pour DELIVERY_REQUEST (et ses suites) : cible une sous-commande
    # précise, pas juste sa commande parente (un Order peut avoir plusieurs
    # sous-commandes, une par vendeur) — voir app/orders/service.py::start_dispatch.
    sub_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sub_orders.id", ondelete="CASCADE"), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
