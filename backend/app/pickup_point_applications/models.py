"""Candidature d'un acheteur pour devenir gestionnaire de point de retrait.

Deux entrées : l'acheteur postule lui-même, ou un admin l'invite par e-mail
(origin = INVITED). Le dossier (identité, pièces, photo d'identité, point de
retrait proposé et photos du local) reste modifiable tant qu'il est en
brouillon ou renvoyé pour correction, puis l'admin tranche :
- APPROVED : le point de retrait est créé, le compte devient gestionnaire ;
- CHANGES_REQUESTED : « seconde chance » — motif + suggestion, le dossier est
  rouvert pour correction puis resoumis ;
- REJECTED : refus définitif du compte (il ne peut plus postuler, seul un
  admin peut encore l'inviter).

Une ligne par compte (user_id unique) : la seconde chance et une nouvelle
invitation réutilisent le même dossier plutôt que d'en empiler.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ARRAY, Date, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base
from app.couriers.models import IdDocumentType


def _enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, values_callable=lambda enum: [e.value for e in enum])


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApplicationOrigin(StrEnum):
    SELF = "self"
    INVITED = "invited"


# Statuts où l'acheteur peut encore modifier son dossier.
EDITABLE_STATUSES = (ApplicationStatus.DRAFT, ApplicationStatus.CHANGES_REQUESTED)


class PickupPointApplication(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pickup_point_applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        _enum(ApplicationStatus, "pickup_application_status"), default=ApplicationStatus.DRAFT, nullable=False
    )
    origin: Mapped[ApplicationOrigin] = mapped_column(
        _enum(ApplicationOrigin, "pickup_application_origin"), default=ApplicationOrigin.SELF, nullable=False
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Identité -------------------------------------------------------------
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    residence_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    id_document_type: Mapped[IdDocumentType | None] = mapped_column(
        _enum(IdDocumentType, "id_document_type"), nullable=True
    )
    id_document_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_document_front_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Obligatoire pour une CNI (recto/verso), pas pour un passeport.
    id_document_back_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Photo d'identité HD fond blanc, format portrait (contrôlée à l'upload).
    portrait_photo_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Point de retrait proposé ----------------------------------------------
    point_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    point_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    point_landmark: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Nombre de colis que le local peut garder en même temps (indicatif).
    storage_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    premises_photo_keys: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    # --- Examen par l'admin ---------------------------------------------------
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submission_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    admin_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    admin_suggestion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Invitation à gérer un point QUI EXISTE DÉJÀ : le candidat ne fournit
    # alors que son identité et ses pièces, la validation le rattache à ce
    # point au lieu d'en créer un. NULL pour une candidature classique.
    target_pickup_point_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pickup_points.id", ondelete="SET NULL"), nullable=True
    )
    # Point créé (ou rattaché) à la validation.
    pickup_point_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pickup_points.id", ondelete="SET NULL"), nullable=True
    )
