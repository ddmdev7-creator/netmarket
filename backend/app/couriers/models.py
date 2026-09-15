"""Courier ORM model — "livreur" (motard, taxi, société de livraison)
transporting a sub-order from a vendor to a buyer or pickup point.

A courier is validated by the admin exactly like a vendor. Assignment to a
sub-order is now proximity-based (see app/orders/service.py::start_dispatch,
which offers the delivery to the nearest online courier first, escalating
down the list if declined/unanswered) rather than the vendor picking blind
from a flat roster — still deliberately simple though: `latitude`/
`longitude` are a one-shot position captured when the courier flips
`is_online` on, not continuous live tracking (cahier des charges §4.2 still
leaves real-time GPS tracking to a later phase).
"""

import uuid
from enum import StrEnum

from sqlalchemy import ARRAY, Boolean, Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class CourierStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class VehicleType(StrEnum):
    MOTO = "moto"
    TAXI = "taxi"
    VOITURE = "voiture"


class IdDocumentType(StrEnum):
    CNI_BIOMETRIQUE = "cni_biometrique"
    PASSEPORT = "passeport"


class Courier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "couriers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    vehicle_type: Mapped[VehicleType] = mapped_column(
        SAEnum(VehicleType, name="vehicle_type", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
    )
    # Zone de couverture textuelle (commune/quartier), même logique que Vendor.zone.
    zone: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[CourierStatus] = mapped_column(
        SAEnum(CourierStatus, name="courier_status", values_callable=lambda enum: [e.value for e in enum]),
        default=CourierStatus.PENDING,
        nullable=False,
    )

    # Vérification d'identité — voir app/couriers/service.py::register_courier.
    # Nullable en base (les livreurs créés directement par un admin, ou
    # existant avant cette itération, n'en ont pas) ; le caractère
    # obligatoire pour l'auto-inscription est imposé par le schéma Pydantic
    # + une garde dans le service, pas par une contrainte SQL.
    id_document_type: Mapped[IdDocumentType | None] = mapped_column(
        SAEnum(IdDocumentType, name="id_document_type", values_callable=lambda enum: [e.value for e in enum]),
        nullable=True,
    )
    id_document_front_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Requis uniquement si id_document_type == CNI_BIOMETRIQUE (un passeport
    # n'a qu'une page photo) — vérifié en service, colonne nullable.
    id_document_back_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Photo de visage fond blanc — pas de traitement automatique pour
    # l'instant (validation admin manuelle uniquement), mais un format
    # standardisé dès maintenant pour un futur rapprochement facial
    # auto-hébergé (voir cahier des charges — pas d'API tierce).
    face_photo_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # Identification de l'engin.
    vehicle_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    vehicle_plate_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vehicle_photo_keys: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    # Motif de rejet, rempli par l'admin — même rôle que Report.admin_note.
    admin_note: Mapped[str | None] = mapped_column(String, nullable=True)

    # Disponibilité + position captée à l'activation — voir
    # app/couriers/service.py::set_availability et
    # app/orders/service.py::start_dispatch (tri des candidats par distance).
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
