"""Schémas des candidatures gestionnaire de point de retrait."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.couriers.models import IdDocumentType
from app.pickup_point_applications.models import ApplicationOrigin, ApplicationStatus


class ApplicationDocumentSlot(StrEnum):
    ID_FRONT = "id_front"
    ID_BACK = "id_back"
    PORTRAIT = "portrait"
    PREMISES = "premises"


class ApplicationDraft(BaseModel):
    """Enregistrement du dossier (brouillon) : tous les champs sont
    optionnels ici, la complétude est vérifiée à la soumission."""

    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    birth_date: date | None = None
    residence_address: str | None = Field(default=None, max_length=300)
    id_document_type: IdDocumentType | None = None
    id_document_number: str | None = Field(default=None, max_length=50)
    id_document_front_key: str | None = None
    id_document_back_key: str | None = None
    portrait_photo_key: str | None = None
    point_name: str | None = Field(default=None, max_length=150)
    point_address: str | None = Field(default=None, max_length=300)
    point_landmark: str | None = Field(default=None, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    opening_hours: str | None = Field(default=None, max_length=300)
    storage_capacity: int | None = Field(default=None, ge=1, le=10_000)
    premises_photo_keys: list[str] = Field(default_factory=list, max_length=8)


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: ApplicationStatus
    origin: ApplicationOrigin
    invited_at: datetime | None
    first_name: str | None
    last_name: str | None
    birth_date: date | None
    residence_address: str | None
    id_document_type: IdDocumentType | None
    id_document_number: str | None
    id_document_front_key: str | None
    id_document_back_key: str | None
    portrait_photo_key: str | None
    point_name: str | None
    point_address: str | None
    point_landmark: str | None
    latitude: float | None
    longitude: float | None
    opening_hours: str | None
    storage_capacity: int | None
    premises_photo_keys: list[str]
    submitted_at: datetime | None
    submission_count: int
    admin_note: str | None
    admin_suggestion: str | None
    reviewed_at: datetime | None
    pickup_point_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MyApplicationState(BaseModel):
    """Où en est l'acheteur : son dossier s'il en a un, et s'il peut postuler."""

    application: ApplicationRead | None
    can_apply: bool
    # Pourquoi il ne peut pas (compte non acheteur, refus définitif…).
    blocked_reason: str | None
    # Règles affichées dans le formulaire.
    min_premises_photos: int
    max_premises_photos: int
    portrait_min_width: int
    portrait_min_height: int


class AdminApplicationRead(ApplicationRead):
    applicant_phone: str
    applicant_email: str | None


class ApplicationInvite(BaseModel):
    email: EmailStr
    message: str | None = Field(default=None, max_length=500)


class ApplicationRequestChanges(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    suggestion: str | None = Field(default=None, max_length=500)


class ApplicationReject(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
