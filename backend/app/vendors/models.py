"""Vendor ORM model."""

import uuid
from enum import StrEnum

from sqlalchemy import Enum as SAEnum, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class VendorStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class Vendor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vendors"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    shop_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[VendorStatus] = mapped_column(
        SAEnum(VendorStatus, name="vendor_status", values_callable=lambda enum: [e.value for e in enum]),
        default=VendorStatus.PENDING,
        nullable=False,
    )
    # Zone textuelle (commune/quartier) plutôt qu'adresse formelle, cf. contraintes marché.
    zone: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Position de la boutique — pour trier les livreurs candidats par distance
    # au moment du dispatch (app/orders/service.py::start_dispatch). Même
    # convention nullable que Address/PickupPoint.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    # Délai de préparation déclaré par le vendeur (en jours), utilisé pour
    # l'estimation de livraison affichée à l'acheteur — voir
    # app/common/delivery_estimate.py. server_default pour que les boutiques
    # déjà existantes récupèrent 1 jour par défaut sans migration de données.
    preparation_days: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
