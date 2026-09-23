"""Candidatures gestionnaire de point de retrait : dossier du candidat
(/pickup-point-applications/me…) et examen par l'admin
(/admin/pickup-point-applications…)."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import fetch_image
from app.pickup_point_applications import repository, service
from app.pickup_point_applications.models import ApplicationStatus
from app.pickup_point_applications.schemas import (
    AdminApplicationRead,
    ApplicationDocumentSlot,
    ApplicationDraft,
    ApplicationInvite,
    ApplicationRead,
    ApplicationReject,
    ApplicationRequestChanges,
    MyApplicationState,
)
from app.uploads.schemas import UploadedImages
from app.users.models import User, UserRole

router = APIRouter(prefix="/pickup-point-applications", tags=["pickup-point-applications"])
admin_router = APIRouter(
    prefix="/admin/pickup-point-applications", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)

_MAX_SIZE_BYTES = 8 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.get("/me", response_model=MyApplicationState)
async def get_my_application(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MyApplicationState:
    return await service.get_my_state(db, current_user)


@router.put("/me", response_model=ApplicationRead)
async def save_my_application(
    payload: ApplicationDraft, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ApplicationRead:
    """Enregistre le dossier (brouillon) — crée la candidature au premier appel."""
    return await service.save_draft(db, current_user, payload)


@router.post("/me/submit", response_model=ApplicationRead)
async def submit_my_application(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ApplicationRead:
    return await service.submit(db, current_user)


@router.post("/me/documents", response_model=UploadedImages, status_code=status.HTTP_201_CREATED)
async def upload_my_documents(
    slot: ApplicationDocumentSlot = Form(...),
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadedImages:
    """Pièce d'identité, photo d'identité (HD, portrait, fond blanc — contrôlée
    ici) ou photos du local. Retourne les clés à mettre dans le dossier."""
    contents: list[tuple[str, bytes]] = []
    for file in files:
        if file.content_type not in _ALLOWED_CONTENT_TYPES:
            raise ConflictError(f"Format non supporté pour « {file.filename} ». Utilise JPEG, PNG ou WebP.")
        content = await file.read()
        if len(content) > _MAX_SIZE_BYTES:
            raise ConflictError(f"« {file.filename} » dépasse la taille maximale de 8 Mo.")
        contents.append((file.filename or "image", content))
    keys = await service.upload_documents(db, current_user, slot, contents)
    return UploadedImages(keys=keys)


@router.get("/{application_id}/documents/{key:path}")
async def get_document(
    application_id: uuid.UUID,
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Jamais public : réservé au candidat et à l'admin, pour une clé de ce dossier."""
    application = await service.get_for_document(db, current_user, application_id)
    if not repository.KEY_PATTERN.match(key) or key not in service.document_keys(application):
        raise NotFoundError("Document introuvable.")
    content = fetch_image(key)
    if content is None:
        raise NotFoundError("Document introuvable.")
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


# --- Admin ----------------------------------------------------------------------


@admin_router.get("", response_model=list[AdminApplicationRead])
async def admin_list_applications(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"), db: AsyncSession = Depends(get_db)
) -> list[AdminApplicationRead]:
    return await service.admin_list(db, status_filter)


@admin_router.get("/{application_id}", response_model=AdminApplicationRead)
async def admin_get_application(application_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminApplicationRead:
    return await service.admin_get(db, application_id)


@admin_router.post("/invite", response_model=AdminApplicationRead, status_code=status.HTTP_201_CREATED)
async def admin_invite(
    payload: ApplicationInvite, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AdminApplicationRead:
    """Invite par e-mail un compte acheteur existant à constituer son dossier."""
    return await service.admin_invite(db, current_user, payload.email, payload.message)


@admin_router.post("/{application_id}/approve", response_model=AdminApplicationRead)
async def admin_approve(
    application_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AdminApplicationRead:
    return await service.admin_approve(db, current_user, application_id)


@admin_router.post("/{application_id}/request-changes", response_model=AdminApplicationRead)
async def admin_request_changes(
    application_id: uuid.UUID,
    payload: ApplicationRequestChanges,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminApplicationRead:
    """Rejet avec seconde chance : motif + suggestion, dossier rouvert."""
    return await service.admin_request_changes(db, current_user, application_id, payload.reason, payload.suggestion)


@admin_router.post("/{application_id}/reject", response_model=AdminApplicationRead)
async def admin_reject(
    application_id: uuid.UUID,
    payload: ApplicationReject,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminApplicationRead:
    """Refus définitif du compte."""
    return await service.admin_reject(db, current_user, application_id, payload.reason)
