"""Business logic for courier ("livreur") onboarding and admin validation."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.couriers import repository
from app.couriers.models import Courier, CourierStatus, IdDocumentType
from app.couriers.schemas import CourierAdminCreate, CourierAdminUpdate, CourierAvailabilityUpdate, CourierRegister
from app.notifications import service as notifications_service
from app.users import repository as users_repository
from app.users.models import User, UserRole


async def register_courier(db: AsyncSession, user: User, data: CourierRegister) -> Courier:
    # Un seul rôle par compte (comme pour les vendeurs) — devenir livreur
    # remplacerait silencieusement le rôle vendeur/admin existant et casserait
    # l'accès aux espaces correspondants. Seul un acheteur peut s'inscrire.
    if user.role == UserRole.COURIER:
        raise ConflictError("Vous êtes déjà inscrit comme livreur.")
    if user.role != UserRole.BUYER:
        raise ForbiddenError("Seul un compte acheteur peut s'inscrire comme livreur.")
    # Un passeport n'a qu'une page photo ; une CNI biométrique a un verso à
    # vérifier également — pas exprimable proprement au niveau du schéma.
    if data.id_document_type == IdDocumentType.CNI_BIOMETRIQUE and not data.id_document_back_key:
        raise ConflictError("Le verso de la carte d'identité biométrique est requis.")

    courier = await repository.create(
        db,
        user_id=user.id,
        vehicle_type=data.vehicle_type,
        zone=data.zone,
        id_document_type=data.id_document_type,
        id_document_front_key=data.id_document_front_key,
        id_document_back_key=data.id_document_back_key,
        face_photo_key=data.face_photo_key,
        vehicle_name=data.vehicle_name,
        vehicle_plate_number=data.vehicle_plate_number,
        vehicle_photo_keys=data.vehicle_photo_keys,
    )
    user.role = UserRole.COURIER
    await db.commit()
    return await repository.get_by_id(db, courier.id)


async def get_my_courier(db: AsyncSession, user: User) -> Courier:
    courier = await repository.get_by_user_id(db, user.id)
    if courier is None:
        raise NotFoundError("Vous n'avez pas encore de profil livreur.")
    return courier


async def list_public_couriers(db: AsyncSession) -> list[Courier]:
    return await repository.list_by_status(db, CourierStatus.APPROVED)


async def set_availability(db: AsyncSession, user: User, data: CourierAvailabilityUpdate) -> Courier:
    courier = await repository.get_by_user_id(db, user.id)
    if courier is None:
        raise NotFoundError("Vous n'avez pas encore de profil livreur.")

    latitude = data.latitude if data.latitude is not None else courier.latitude
    longitude = data.longitude if data.longitude is not None else courier.longitude
    if data.is_online and (latitude is None or longitude is None):
        raise ConflictError("Position GPS requise pour passer disponible.")

    courier.is_online = data.is_online
    courier.latitude = latitude
    courier.longitude = longitude
    await db.commit()
    return await repository.get_by_id(db, courier.id)


async def admin_create_courier(db: AsyncSession, data: CourierAdminCreate) -> Courier:
    if await users_repository.get_by_phone(db, data.phone) is not None:
        raise ConflictError("Ce numéro de téléphone est déjà utilisé.")

    user = await users_repository.create(
        db,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.COURIER,
        first_name=data.first_name,
        last_name=data.last_name,
    )
    courier = await repository.create(db, user_id=user.id, vehicle_type=data.vehicle_type, zone=data.zone)
    # Un admin qui crée le compte EST la validation — pas besoin de repasser
    # par le statut pending comme pour l'auto-inscription.
    courier.status = CourierStatus.APPROVED
    await db.commit()
    return await repository.get_by_id(db, courier.id)


async def admin_list_couriers(db: AsyncSession, status: CourierStatus | None) -> list[Courier]:
    return await repository.list_by_status(db, status)


async def admin_update_courier(db: AsyncSession, courier_id: uuid.UUID, data: CourierAdminUpdate) -> Courier:
    courier = await repository.get_by_id(db, courier_id)
    if courier is None:
        raise NotFoundError("Livreur introuvable.")
    if data.status == CourierStatus.REJECTED and not data.admin_note:
        raise ConflictError("Un motif de refus est requis.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(courier, field, value)
    await db.commit()

    if data.status == CourierStatus.APPROVED:
        await notifications_service.notify_courier_verification_approved(db, courier_user_id=courier.user_id)
    elif data.status == CourierStatus.REJECTED:
        await notifications_service.notify_courier_verification_rejected(
            db, courier_user_id=courier.user_id, admin_note=data.admin_note
        )

    return await repository.get_by_id(db, courier_id)
