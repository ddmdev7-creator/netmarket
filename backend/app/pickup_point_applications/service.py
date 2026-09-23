"""Candidatures gestionnaire de point de retrait — voir models.py pour le
cycle de vie (brouillon → soumis → validé / seconde chance / refus définitif)."""

import io
import logging
import uuid
from datetime import UTC, datetime

from PIL import Image, ImageStat, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import send_email
from app.core.email_templates import pickup_application_email
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.storage import upload_image
from app.couriers.models import IdDocumentType
from app.notifications import service as notifications_service
from app.notifications.models import NotificationType
from app.pickup_point_applications import repository
from app.pickup_point_applications.models import (
    EDITABLE_STATUSES,
    ApplicationOrigin,
    ApplicationStatus,
    PickupPointApplication,
)
from app.pickup_point_applications.schemas import (
    AdminApplicationRead,
    ApplicationDocumentSlot,
    ApplicationDraft,
    ApplicationRead,
    MyApplicationState,
)
from app.pickup_point_managers import repository as managers_repository
from app.pickup_points import repository as pickup_points_repository
from app.users import repository as users_repository
from app.users.models import User, UserRole

settings = get_settings()
logger = logging.getLogger(__name__)

STORAGE_PREFIX = "pickup-applications/"
MIN_PREMISES_PHOTOS = 4
MAX_PREMISES_PHOTOS = 8
# Photo d'identité « format carte » en HD : portrait ~3,5 × 4,5 cm, soit un
# ratio largeur/hauteur autour de 0,78 ; au moins 600 × 800 px.
PORTRAIT_MIN_WIDTH = 600
PORTRAIT_MIN_HEIGHT = 800
_PORTRAIT_RATIO_RANGE = (0.65, 0.90)
# Fond blanc : bandes de bord claires (luminance) et peu colorées.
_WHITE_MIN_LUMINANCE = 200
_WHITE_MAX_CHROMA = 30
PREMISES_MIN_DIMENSION = 640

_SLOT_MAX_FILES = {
    ApplicationDocumentSlot.ID_FRONT: 1,
    ApplicationDocumentSlot.ID_BACK: 1,
    ApplicationDocumentSlot.PORTRAIT: 1,
    ApplicationDocumentSlot.PREMISES: MAX_PREMISES_PHOTOS,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _read(application: PickupPointApplication) -> ApplicationRead:
    return ApplicationRead.model_validate(application)


# --- Côté candidat -----------------------------------------------------------------


def _blocked_reason(user: User, application: PickupPointApplication | None) -> str | None:
    if application is not None and application.status == ApplicationStatus.APPROVED:
        return "Votre candidature a été validée : vous gérez déjà un point de retrait."
    if application is not None and application.status == ApplicationStatus.REJECTED:
        return "Votre candidature a été refusée définitivement."
    if user.role != UserRole.BUYER:
        return "Seul un compte acheteur peut postuler pour gérer un point de retrait."
    return None


async def get_my_state(db: AsyncSession, user: User) -> MyApplicationState:
    application = await repository.get_by_user_id(db, user.id)
    reason = _blocked_reason(user, application)
    return MyApplicationState(
        application=_read(application) if application else None,
        can_apply=reason is None,
        blocked_reason=reason,
        min_premises_photos=MIN_PREMISES_PHOTOS,
        max_premises_photos=MAX_PREMISES_PHOTOS,
        portrait_min_width=PORTRAIT_MIN_WIDTH,
        portrait_min_height=PORTRAIT_MIN_HEIGHT,
    )


async def _editable_application(db: AsyncSession, user: User) -> PickupPointApplication:
    """Dossier modifiable de l'utilisateur (créé à la première sauvegarde)."""
    application = await repository.get_by_user_id(db, user.id, for_update=True)
    reason = _blocked_reason(user, application)
    if reason is not None:
        raise ForbiddenError(reason)
    if application is None:
        application = PickupPointApplication(
            user_id=user.id, first_name=user.first_name, last_name=user.last_name, premises_photo_keys=[]
        )
        repository.add(db, application)
        await db.flush()
    elif application.status not in EDITABLE_STATUSES:
        raise ConflictError("Votre dossier est en cours d'examen : il n'est plus modifiable pour le moment.")
    return application


def _check_own_keys(user: User, keys: list[str | None]) -> None:
    """Les clés de documents viennent de /me/documents : préfixe attendu,
    rien d'autre (on n'accepte pas une clé d'un autre espace de stockage)."""
    for key in keys:
        if key is not None and not repository.KEY_PATTERN.match(key):
            raise ConflictError("Document invalide : ré-envoyez le fichier.")


async def save_draft(db: AsyncSession, user: User, data: ApplicationDraft) -> ApplicationRead:
    application = await _editable_application(db, user)
    _check_own_keys(
        user,
        [data.id_document_front_key, data.id_document_back_key, data.portrait_photo_key, *data.premises_photo_keys],
    )
    for field, value in data.model_dump().items():
        setattr(application, field, value.strip() if isinstance(value, str) else value)
    await db.commit()
    await db.refresh(application)
    return _read(application)


def _missing_fields(application: PickupPointApplication) -> list[str]:
    missing = []
    required = {
        "first_name": "prénom",
        "last_name": "nom",
        "birth_date": "date de naissance",
        "residence_address": "adresse personnelle",
        "id_document_type": "type de pièce d'identité",
        "id_document_number": "numéro de pièce",
        "id_document_front_key": "pièce d'identité (recto)",
        "portrait_photo_key": "photo d'identité",
        "point_name": "nom du point de retrait",
        "point_address": "adresse du point de retrait",
        "opening_hours": "horaires d'ouverture",
    }
    for field, label in required.items():
        if not getattr(application, field):
            missing.append(label)
    if application.id_document_type == IdDocumentType.CNI_BIOMETRIQUE and not application.id_document_back_key:
        missing.append("pièce d'identité (verso)")
    if application.latitude is None or application.longitude is None:
        missing.append("position du point sur la carte")
    if len(application.premises_photo_keys) < MIN_PREMISES_PHOTOS:
        missing.append(f"au moins {MIN_PREMISES_PHOTOS} photos du local")
    return missing


async def submit(db: AsyncSession, user: User) -> ApplicationRead:
    application = await _editable_application(db, user)
    missing = _missing_fields(application)
    if missing:
        raise ConflictError("Dossier incomplet : " + ", ".join(missing) + ".")
    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = _now()
    application.submission_count += 1
    await db.commit()
    await db.refresh(application)

    for admin in await users_repository.list_by_role(db, UserRole.ADMIN):
        await notifications_service.notify_pickup_application(
            db,
            user_id=admin.id,
            type_=NotificationType.PICKUP_APPLICATION_SUBMITTED,
            title="Candidature point de retrait à examiner",
            body=f"« {application.point_name} » — {application.first_name} {application.last_name}"
            + (" (dossier corrigé)" if application.submission_count > 1 else ""),
        )
    return _read(application)


def _check_portrait(content: bytes) -> None:
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
    except UnidentifiedImageError as exc:
        raise ConflictError("La photo d'identité n'est pas une image valide.") from exc
    width, height = image.size
    if width < PORTRAIT_MIN_WIDTH or height < PORTRAIT_MIN_HEIGHT:
        raise ConflictError(
            f"Photo d'identité trop petite : au moins {PORTRAIT_MIN_WIDTH} × {PORTRAIT_MIN_HEIGHT} px "
            f"(reçue : {width} × {height})."
        )
    ratio = width / height
    if not _PORTRAIT_RATIO_RANGE[0] <= ratio <= _PORTRAIT_RATIO_RANGE[1]:
        raise ConflictError("La photo d'identité doit être au format portrait (type photo de carte d'identité).")
    # Fond blanc : on regarde les bandes du haut et des côtés (le bas est
    # souvent occupé par les épaules).
    band = max(8, width // 12)
    regions = [(0, 0, width, band), (0, 0, band, height // 2), (width - band, 0, width, height // 2)]
    for box in regions:
        r, g, b = ImageStat.Stat(image.crop(box)).mean
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        chroma = max(r, g, b) - min(r, g, b)
        if luminance < _WHITE_MIN_LUMINANCE or chroma > _WHITE_MAX_CHROMA:
            raise ConflictError("La photo d'identité doit être prise sur un fond blanc uni.")


def _check_min_dimension(content: bytes, minimum: int, label: str) -> None:
    try:
        width, height = Image.open(io.BytesIO(content)).size
    except UnidentifiedImageError as exc:
        raise ConflictError(f"{label} : ce n'est pas une image valide.") from exc
    if max(width, height) < minimum:
        raise ConflictError(f"{label} : image trop petite (au moins {minimum} px sur le grand côté).")


async def upload_documents(
    db: AsyncSession, user: User, slot: ApplicationDocumentSlot, files: list[tuple[str, bytes]]
) -> list[str]:
    await _editable_application(db, user)
    await db.commit()
    if len(files) > _SLOT_MAX_FILES[slot]:
        raise ConflictError(f"Maximum {_SLOT_MAX_FILES[slot]} fichier(s) pour cette pièce.")
    keys = []
    for filename, content in files:
        if slot == ApplicationDocumentSlot.PORTRAIT:
            _check_portrait(content)
        elif slot == ApplicationDocumentSlot.PREMISES:
            _check_min_dimension(content, PREMISES_MIN_DIMENSION, f"« {filename} »")
        try:
            keys.append(upload_image(content, prefix=STORAGE_PREFIX))
        except UnidentifiedImageError as exc:
            raise ConflictError(f"« {filename} » n'est pas une image valide.") from exc
    return keys


def document_keys(application: PickupPointApplication) -> set[str]:
    keys = {application.id_document_front_key, application.id_document_back_key, application.portrait_photo_key}
    keys.update(application.premises_photo_keys)
    return {k for k in keys if k}


async def get_for_document(db: AsyncSession, user: User, application_id: uuid.UUID) -> PickupPointApplication:
    application = await repository.get_by_id(db, application_id)
    if application is None:
        raise NotFoundError("Candidature introuvable.")
    if user.role != UserRole.ADMIN and application.user_id != user.id:
        raise ForbiddenError("Vous n'avez pas accès à ce document.")
    return application


# --- Côté admin -------------------------------------------------------------------------


async def _admin_read(db: AsyncSession, application: PickupPointApplication) -> AdminApplicationRead:
    applicant = await users_repository.get_by_id(db, application.user_id)
    return AdminApplicationRead(
        **ApplicationRead.model_validate(application).model_dump(),
        applicant_phone=applicant.phone if applicant else "—",
        applicant_email=applicant.email if applicant else None,
    )


async def admin_list(db: AsyncSession, status: ApplicationStatus | None) -> list[AdminApplicationRead]:
    return [await _admin_read(db, a) for a in await repository.list_all(db, status)]


async def _get_for_admin(db: AsyncSession, application_id: uuid.UUID) -> PickupPointApplication:
    application = await repository.get_by_id(db, application_id, for_update=True)
    if application is None:
        raise NotFoundError("Candidature introuvable.")
    return application


async def admin_get(db: AsyncSession, application_id: uuid.UUID) -> AdminApplicationRead:
    return await _admin_read(db, await _get_for_admin(db, application_id))


def _application_url() -> str:
    return f"{settings.frontend_url}/point-retrait/candidature"


async def _email(user: User, *, heading: str, paragraphs: list[str], cta_label: str) -> None:
    if not user.email:
        return
    subject, text, html_body = pickup_application_email(
        heading=heading, paragraphs=paragraphs, cta_label=cta_label, cta_url=_application_url()
    )
    try:
        await send_email(user.email, subject, text, html_body)
    except Exception:  # noqa: BLE001 — l'e-mail est un complément de la notification in-app
        logger.warning("E-mail de candidature non envoyé à %s", user.email, exc_info=True)


async def admin_invite(db: AsyncSession, admin: User, email: str, message: str | None) -> AdminApplicationRead:
    """Invite un compte acheteur existant à constituer son dossier. Rouvre un
    dossier refusé définitivement (l'admin est seul à pouvoir le faire)."""
    user = await users_repository.get_by_email_insensitive(db, email)
    if user is None:
        raise NotFoundError("Aucun compte avec cet e-mail : la personne doit d'abord créer un compte acheteur.")
    if user.role != UserRole.BUYER:
        raise ConflictError("Ce compte n'est pas un compte acheteur.")
    application = await repository.get_by_user_id(db, user.id, for_update=True)
    if application is None:
        application = PickupPointApplication(
            user_id=user.id, first_name=user.first_name, last_name=user.last_name, premises_photo_keys=[]
        )
        repository.add(db, application)
    elif application.status == ApplicationStatus.APPROVED:
        raise ConflictError("Ce compte gère déjà un point de retrait.")
    elif application.status == ApplicationStatus.SUBMITTED:
        raise ConflictError("Ce compte a déjà un dossier en cours d'examen.")
    elif application.status == ApplicationStatus.REJECTED:
        application.status = ApplicationStatus.DRAFT
    application.origin = ApplicationOrigin.INVITED
    application.invited_by = admin.id
    application.invited_at = _now()
    await db.commit()
    await db.refresh(application)

    body = "L'équipe Ndjouri vous invite à devenir gestionnaire d'un point de retrait. Complétez votre dossier depuis votre espace."
    await notifications_service.notify_pickup_application(
        db, user_id=user.id, type_=NotificationType.PICKUP_APPLICATION_INVITED, title="Devenez point de retrait", body=body
    )
    paragraphs = [
        "L'équipe Ndjouri vous invite à devenir gestionnaire d'un point de retrait : vous recevrez les colis des "
        "clients de votre quartier et serez rémunéré pour chaque colis remis.",
        "Pour postuler, connectez-vous et complétez votre dossier : pièce d'identité, photo d'identité, adresse du "
        "point et photos du local.",
    ]
    if message:
        paragraphs.insert(1, f"Message de l'équipe : {message}")
    await _email(user, heading="Invitation : devenez point de retrait", paragraphs=paragraphs, cta_label="Compléter mon dossier")
    return await _admin_read(db, application)


async def admin_approve(db: AsyncSession, admin: User, application_id: uuid.UUID) -> AdminApplicationRead:
    application = await _get_for_admin(db, application_id)
    if application.status != ApplicationStatus.SUBMITTED:
        raise ConflictError("Seul un dossier soumis peut être validé.")
    user = await users_repository.get_by_id(db, application.user_id)
    if user is None:
        raise NotFoundError("Compte du candidat introuvable.")
    if user.role != UserRole.BUYER or await managers_repository.get_by_user_id(db, user.id) is not None:
        raise ConflictError("Ce compte a changé de rôle depuis sa candidature : validation impossible.")

    zone = application.point_address or ""
    if application.point_landmark:
        zone = f"{zone} — {application.point_landmark}"
    point = await pickup_points_repository.create(
        db,
        name=application.point_name,
        zone=zone[:300],
        latitude=application.latitude,
        longitude=application.longitude,
        opening_hours=application.opening_hours,
        is_active=True,
    )
    await managers_repository.create(db, user_id=user.id, pickup_point_id=point.id)
    user.role = UserRole.PICKUP_POINT_MANAGER
    user.first_name = user.first_name or application.first_name
    user.last_name = user.last_name or application.last_name
    application.status = ApplicationStatus.APPROVED
    application.pickup_point_id = point.id
    application.admin_note = None
    application.admin_suggestion = None
    application.reviewed_by = admin.id
    application.reviewed_at = _now()
    await db.commit()
    await db.refresh(application)

    await notifications_service.notify_pickup_application(
        db,
        user_id=user.id,
        type_=NotificationType.PICKUP_APPLICATION_APPROVED,
        title="Candidature validée",
        body=f"« {point.name} » est maintenant un point de retrait Ndjouri. Bienvenue !",
    )
    await _email(
        user,
        heading="Votre point de retrait est validé",
        paragraphs=[
            f"Bonne nouvelle : « {point.name} » est maintenant un point de retrait Ndjouri.",
            "Reconnectez-vous pour accéder à votre espace gestionnaire : colis attendus, colis en stock et remises aux clients.",
        ],
        cta_label="Ouvrir mon espace",
    )
    return await _admin_read(db, application)


async def admin_request_changes(
    db: AsyncSession, admin: User, application_id: uuid.UUID, reason: str, suggestion: str | None
) -> AdminApplicationRead:
    """Rejet avec seconde chance : le dossier est rouvert pour correction."""
    application = await _get_for_admin(db, application_id)
    if application.status != ApplicationStatus.SUBMITTED:
        raise ConflictError("Seul un dossier soumis peut être renvoyé pour correction.")
    application.status = ApplicationStatus.CHANGES_REQUESTED
    application.admin_note = reason.strip()
    application.admin_suggestion = suggestion.strip() if suggestion else None
    application.reviewed_by = admin.id
    application.reviewed_at = _now()
    await db.commit()
    await db.refresh(application)

    user = await users_repository.get_by_id(db, application.user_id)
    await notifications_service.notify_pickup_application(
        db,
        user_id=application.user_id,
        type_=NotificationType.PICKUP_APPLICATION_CHANGES_REQUESTED,
        title="Dossier à corriger",
        body=f"Motif : {application.admin_note}",
    )
    if user is not None:
        paragraphs = [f"Votre dossier de point de retrait doit être corrigé. Motif : {application.admin_note}"]
        if application.admin_suggestion:
            paragraphs.append(f"Notre suggestion : {application.admin_suggestion}")
        paragraphs.append("Votre dossier est rouvert : corrigez-le puis soumettez-le à nouveau.")
        await _email(user, heading="Votre dossier est à corriger", paragraphs=paragraphs, cta_label="Corriger mon dossier")
    return await _admin_read(db, application)


async def admin_reject(db: AsyncSession, admin: User, application_id: uuid.UUID, reason: str) -> AdminApplicationRead:
    """Refus définitif : le compte ne peut plus postuler (seule une nouvelle
    invitation de l'admin rouvre le dossier)."""
    application = await _get_for_admin(db, application_id)
    if application.status not in (ApplicationStatus.SUBMITTED, *EDITABLE_STATUSES):
        raise ConflictError("Cette candidature ne peut plus être refusée.")
    application.status = ApplicationStatus.REJECTED
    application.admin_note = reason.strip()
    application.admin_suggestion = None
    application.reviewed_by = admin.id
    application.reviewed_at = _now()
    await db.commit()
    await db.refresh(application)

    user = await users_repository.get_by_id(db, application.user_id)
    await notifications_service.notify_pickup_application(
        db,
        user_id=application.user_id,
        type_=NotificationType.PICKUP_APPLICATION_REJECTED,
        title="Candidature refusée",
        body=f"Motif : {application.admin_note}",
    )
    if user is not None:
        await _email(
            user,
            heading="Votre candidature n'a pas été retenue",
            paragraphs=[
                f"Votre candidature de point de retrait a été refusée. Motif : {application.admin_note}",
                "Ce refus est définitif pour ce compte.",
            ],
            cta_label="Voir ma candidature",
        )
    return await _admin_read(db, application)
