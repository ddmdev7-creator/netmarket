"""Pydantic schemas for courier ("livreur") onboarding and admin validation."""

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.auth.schemas import PHONE_PATTERN
from app.couriers.models import CourierStatus, IdDocumentType, VehicleType


class CourierDocumentSlot(StrEnum):
    """Où range-t-on le fichier uploadé — voir POST /couriers/me/documents.
    Détermine la limite de fichiers acceptés (1, sauf "vehicle": jusqu'à 4)."""

    ID_FRONT = "id_front"
    ID_BACK = "id_back"
    FACE = "face"
    VEHICLE = "vehicle"


class CourierRegister(BaseModel):
    vehicle_type: VehicleType
    zone: str | None = Field(default=None, max_length=150)
    # Vérification d'identité — voir app/couriers/service.py::register_courier
    # pour la garde "verso requis si CNI" (pas exprimable proprement ici).
    id_document_type: IdDocumentType
    id_document_front_key: str
    id_document_back_key: str | None = None
    face_photo_key: str
    vehicle_name: str = Field(min_length=1, max_length=150)
    vehicle_plate_number: str = Field(min_length=1, max_length=50)
    vehicle_photo_keys: list[str] = Field(min_length=1, max_length=4)


class CourierAdminCreate(BaseModel):
    """Admin-direct account creation — e.g. for a partner delivery company
    that shouldn't have to self-register as a buyer first. Approved immediately
    (an admin creating the account IS the validation), unlike self-registration."""

    phone: str = Field(pattern=PHONE_PATTERN, description="Format international, ex: +224621234567")
    password: str = Field(min_length=8)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    vehicle_type: VehicleType
    zone: str | None = Field(default=None, max_length=150)


class CourierAdminUpdate(BaseModel):
    status: CourierStatus | None = None
    # Requis quand status == REJECTED — voir service.admin_update_courier.
    admin_note: str | None = Field(default=None, max_length=300)


class CourierAvailabilityUpdate(BaseModel):
    """Bascule "disponible/indisponible" — voir service.set_availability.
    Passer en ligne sans coordonnées (ni nouvelles ni déjà enregistrées) est
    rejeté par le service ; les repasser à chaque fois qu'il se remet en
    ligne garde sa position à jour sans tracking continu."""

    is_online: bool
    latitude: float | None = None
    longitude: float | None = None


class CourierRead(BaseModel):
    """Vue publique (annuaire /couriers consulté par les vendeurs pour
    choisir qui livre leur sous-commande) — volontairement sans les champs de
    vérification d'identité, voir CourierDetailRead pour ça."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    vehicle_type: VehicleType
    zone: str | None
    status: CourierStatus
    is_online: bool
    # Attachés en lecture depuis User (voir app/couriers/repository.py) — un
    # vendeur choisissant un livreur dans une liste a besoin de plus qu'un id.
    phone: str
    full_name: str | None = None


class CourierDetailRead(CourierRead):
    """Vue complète — le livreur lui-même (/couriers/me) et l'admin
    uniquement. Ne jamais utiliser pour l'annuaire public."""

    id_document_type: IdDocumentType | None
    id_document_front_key: str | None
    id_document_back_key: str | None
    face_photo_key: str | None
    vehicle_name: str | None
    vehicle_plate_number: str | None
    vehicle_photo_keys: list[str]
    admin_note: str | None
    latitude: float | None
    longitude: float | None
