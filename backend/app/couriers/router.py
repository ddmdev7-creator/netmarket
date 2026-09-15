"""Courier ("livreur") endpoints: self-registration, public directory (for
vendors picking who delivers their sub-order), identity/vehicle document
upload, and admin validation.
"""

import io
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.storage import fetch_image, upload_image
from app.couriers import repository, service
from app.couriers.models import Courier, CourierStatus
from app.couriers.schemas import (
    CourierAdminCreate,
    CourierAdminUpdate,
    CourierAvailabilityUpdate,
    CourierDetailRead,
    CourierDocumentSlot,
    CourierRead,
    CourierRegister,
)
from app.uploads.schemas import UploadedImages
from app.users.models import User, UserRole

router = APIRouter(prefix="/couriers", tags=["couriers"])
admin_router = APIRouter(
    prefix="/admin/couriers", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)

_STORAGE_PREFIX = "courier-docs/"
_KEY_PATTERN = re.compile(r"^courier-docs/[0-9a-f-]{36}\.jpg$")
_MAX_SIZE_BYTES = 8 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
# 1 fichier pour chaque pièce/photo de visage, jusqu'à 4 pour l'engin.
_SLOT_MAX_FILES = {
    CourierDocumentSlot.ID_FRONT: 1,
    CourierDocumentSlot.ID_BACK: 1,
    CourierDocumentSlot.FACE: 1,
    CourierDocumentSlot.VEHICLE: 4,
}
# Résolution minimale, petit côté — seulement pour la photo de visage : c'est
# la seule pensée pour un futur traitement automatique (voir cahier des
# charges), les pièces d'identité et photos d'engin n'ont pas cette contrainte.
_FACE_MIN_DIMENSION = 480


@router.post("/me", response_model=CourierDetailRead, status_code=status.HTTP_201_CREATED)
async def register_courier(
    payload: CourierRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CourierDetailRead:
    return await service.register_courier(db, current_user, payload)


@router.get("/me", response_model=CourierDetailRead)
async def get_my_courier(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CourierDetailRead:
    return await service.get_my_courier(db, current_user)


@router.patch("/me/availability", response_model=CourierDetailRead, dependencies=[Depends(require_role(UserRole.COURIER))])
async def set_availability(
    payload: CourierAvailabilityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CourierDetailRead:
    return await service.set_availability(db, current_user, payload)


@router.post("/me/documents", response_model=UploadedImages, dependencies=[Depends(require_role(UserRole.BUYER))])
async def upload_courier_documents(
    slot: CourierDocumentSlot = Form(...), files: list[UploadFile] = File(...)
) -> UploadedImages:
    """Étape préalable à POST /couriers/me : upload la pièce d'identité, la
    photo de visage, ou les photos de l'engin, retourne les clés à inclure
    dans CourierRegister. Distinct de POST /uploads/images (photos produit,
    servies publiquement) — ces documents sont sensibles, voir
    GET /couriers/{id}/documents/{key} pour la lecture (jamais publique)."""
    max_files = _SLOT_MAX_FILES[slot]
    if len(files) > max_files:
        raise ConflictError(f"Maximum {max_files} fichier(s) pour cette pièce.")

    keys: list[str] = []
    for file in files:
        if file.content_type not in _ALLOWED_CONTENT_TYPES:
            raise ConflictError(f"Format non supporté pour « {file.filename} ». Utilise JPEG, PNG ou WebP.")

        content = await file.read()
        if len(content) > _MAX_SIZE_BYTES:
            raise ConflictError(f"« {file.filename} » dépasse la taille maximale de 8 Mo.")

        if slot == CourierDocumentSlot.FACE:
            try:
                width, height = Image.open(io.BytesIO(content)).size
            except UnidentifiedImageError as exc:
                raise ConflictError(f"« {file.filename} » n'est pas une image valide.") from exc
            if min(width, height) < _FACE_MIN_DIMENSION:
                raise ConflictError(
                    f"La photo de visage doit faire au moins {_FACE_MIN_DIMENSION}px sur son plus petit côté."
                )

        try:
            keys.append(upload_image(content, prefix=_STORAGE_PREFIX))
        except UnidentifiedImageError as exc:
            raise ConflictError(f"« {file.filename} » n'est pas une image valide.") from exc

    return UploadedImages(keys=keys)


def _courier_document_keys(courier: Courier) -> set[str]:
    keys = {courier.id_document_front_key, courier.id_document_back_key, courier.face_photo_key}
    keys.update(courier.vehicle_photo_keys)
    return {k for k in keys if k}


@router.get("/{courier_id}/documents/{key:path}")
async def get_courier_document(
    courier_id: uuid.UUID,
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Jamais public, contrairement à GET /uploads/images/{key} : réservé à
    l'admin et au livreur concerné, et seulement pour une clé qui lui
    appartient réellement (défense en profondeur si une clé était réutilisée
    par erreur entre deux livreurs)."""
    courier = await repository.get_by_id(db, courier_id)
    if courier is None:
        raise NotFoundError("Livreur introuvable.")
    if current_user.role != UserRole.ADMIN and courier.user_id != current_user.id:
        raise ForbiddenError("Vous n'avez pas accès à ce document.")
    if not _KEY_PATTERN.match(key) or key not in _courier_document_keys(courier):
        raise NotFoundError("Document introuvable.")

    content = fetch_image(key)
    if content is None:
        raise NotFoundError("Document introuvable.")
    # Contrairement aux photos produit : jamais de cache partagé/persistant
    # pour une pièce d'identité ou une photo de visage.
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.get("", response_model=list[CourierRead])
async def list_couriers(db: AsyncSession = Depends(get_db)) -> list[CourierRead]:
    return await service.list_public_couriers(db)


@admin_router.post("", response_model=CourierDetailRead, status_code=status.HTTP_201_CREATED)
async def admin_create_courier(payload: CourierAdminCreate, db: AsyncSession = Depends(get_db)) -> CourierDetailRead:
    return await service.admin_create_courier(db, payload)


@admin_router.get("", response_model=list[CourierDetailRead])
async def admin_list_couriers(
    status_filter: CourierStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[CourierDetailRead]:
    return await service.admin_list_couriers(db, status_filter)


@admin_router.patch("/{courier_id}", response_model=CourierDetailRead)
async def admin_update_courier(
    courier_id: uuid.UUID, payload: CourierAdminUpdate, db: AsyncSession = Depends(get_db)
) -> CourierDetailRead:
    return await service.admin_update_courier(db, courier_id, payload)
