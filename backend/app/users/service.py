"""Business logic for the authenticated user's own profile, plus one-time email
codes: verification (triggered at registration — see app/auth/service.py::register_user
— and vendor onboarding, app/vendors/service.py::register_vendor) and password
reset (app/auth/service.py::forgot_password/reset_password)."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.core.email_templates import verification_code_email
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.pickup_point_managers import repository as pickup_point_manager_repository
from app.users import repository
from app.users.models import EmailCodePurpose, User, UserRole
from app.users.schemas import AdminPasswordReset, UserUpdate

CODE_LENGTH = 5
CODE_TTL_MINUTES = 15
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await repository.get_by_id(db, user_id)
    if user is None:
        raise NotFoundError("Utilisateur introuvable.")
    return user


async def get_my_profile(db: AsyncSession, user: User) -> User:
    """Same object as `user`, with is_pickup_point_manager attached — a plain
    `return current_user` at the router wouldn't carry this transient field."""
    user.is_pickup_point_manager = await pickup_point_manager_repository.get_by_user_id(db, user.id) is not None
    return user


async def update_profile(db: AsyncSession, user: User, data: UserUpdate) -> User:
    if data.email is not None and data.email != user.email:
        existing = await repository.get_by_email(db, data.email)
        if existing is not None and existing.id != user.id:
            raise ConflictError("Cet email est déjà utilisé.")
        user.email = data.email

    for field in ("first_name", "last_name"):
        value = getattr(data, field)
        if field in data.model_fields_set:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


def _generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


async def create_code(db: AsyncSession, user: User, purpose: EmailCodePurpose) -> str:
    """Generate, store and return a fresh code for this (user, purpose) — also used by
    app/auth/service.py::forgot_password for password-reset codes."""
    existing = await repository.get_email_code(db, user.id, purpose)
    if existing is not None:
        age = datetime.now(timezone.utc) - existing.created_at
        if age < timedelta(seconds=RESEND_COOLDOWN_SECONDS):
            wait = RESEND_COOLDOWN_SECONDS - int(age.total_seconds())
            raise ConflictError(f"Merci de patienter {wait} secondes avant de redemander un code.")

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
    await repository.put_email_code(db, user.id, purpose, code_hash=hash_password(code), expires_at=expires_at)
    await db.commit()
    return code


async def consume_code(db: AsyncSession, user: User, purpose: EmailCodePurpose, code: str) -> None:
    """Validate and delete this (user, purpose) code, or raise — also used by
    app/auth/service.py::reset_password for password-reset codes."""
    record = await repository.get_email_code(db, user.id, purpose)
    if record is None:
        raise ConflictError("Aucun code en attente. Demande un nouveau code.")

    if datetime.now(timezone.utc) > record.expires_at:
        await repository.delete_email_code(db, record)
        await db.commit()
        raise ConflictError("Ce code a expiré. Demande un nouveau code.")

    if record.attempts >= MAX_ATTEMPTS:
        await repository.delete_email_code(db, record)
        await db.commit()
        raise ConflictError("Trop de tentatives. Demande un nouveau code.")

    if not verify_password(code, record.code_hash):
        record.attempts += 1
        await db.commit()
        raise ConflictError("Code incorrect.")

    await repository.delete_email_code(db, record)
    await db.commit()


async def send_verification_code(db: AsyncSession, user: User) -> None:
    if not user.email:
        raise ConflictError("Aucun email renseigné sur ce compte.")

    code = await create_code(db, user, EmailCodePurpose.EMAIL_VERIFICATION)
    subject, text, html = verification_code_email(code, CODE_TTL_MINUTES)
    await send_email(user.email, subject, text, html)


async def verify_email_code(db: AsyncSession, user: User, code: str) -> User:
    await consume_code(db, user, EmailCodePurpose.EMAIL_VERIFICATION, code)
    user.email_verified = True
    await db.commit()
    await db.refresh(user)
    return user


async def admin_list_users(db: AsyncSession) -> list[User]:
    return await repository.list_all(db)


async def admin_delete_user(db: AsyncSession, admin: User, target_user_id: uuid.UUID) -> None:
    if target_user_id == admin.id:
        raise ForbiddenError("Vous ne pouvez pas supprimer votre propre compte.")

    target = await repository.get_by_id(db, target_user_id)
    if target is None:
        raise NotFoundError("Utilisateur introuvable.")

    # Un compte admin ne se supprime pas via cette route — garde-fou
    # délibéré pour ne jamais se retrouver sans aucun accès admin après un
    # nettoyage en masse (voir la demande "garder les admins" côté produit).
    if target.role == UserRole.ADMIN:
        raise ForbiddenError("Impossible de supprimer un compte administrateur via cette route.")

    await repository.purge_user(db, target)
    await db.commit()


async def admin_reset_password(db: AsyncSession, target_user_id: uuid.UUID, data: AdminPasswordReset) -> None:
    target = await repository.get_by_id(db, target_user_id)
    if target is None:
        raise NotFoundError("Utilisateur introuvable.")

    target.password_hash = hash_password(data.new_password)
    await db.commit()
