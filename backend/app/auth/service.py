"""Registration, login and token refresh business logic.

Self-registration always creates a buyer account. Promoting a user to vendor
is handled by a dedicated flow (vendor onboarding), not exposed here, so a
client can never grant itself elevated privileges. The one exception is the
admin role: since there is no admin account to promote a user *to* on a fresh
deployment, `bootstrap_admin` below creates it directly, gated by a secret
(`ADMIN_BOOTSTRAP_TOKEN`) instead of an authenticated admin session.
"""

import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AdminBootstrapRequest, LoginRequest, RegisterRequest, TokenPair
from app.core.config import get_settings
from app.core.email import send_email
from app.core.email_templates import password_reset_email
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.users import repository
from app.users import service as user_service
from app.users.models import EmailCodePurpose, User, UserRole

INVALID_CREDENTIALS_MESSAGE = "Numéro de téléphone ou mot de passe incorrect."


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    if await repository.get_by_phone(db, data.phone) is not None:
        raise ConflictError("Ce numéro de téléphone est déjà utilisé.")
    if await repository.get_by_email(db, data.email) is not None:
        raise ConflictError("Cet email est déjà utilisé.")

    user = await repository.create(
        db,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.BUYER,
        email=data.email,
    )
    await db.commit()
    await db.refresh(user)

    await user_service.send_verification_code(db, user)

    return user


async def bootstrap_admin(db: AsyncSession, data: AdminBootstrapRequest, *, provided_token: str | None) -> User:
    """One-time creation of the first admin account, gated by ADMIN_BOOTSTRAP_TOKEN
    instead of an authenticated admin session (there is none yet on a fresh
    deployment). Refuses once an admin already exists — from then on, admin
    accounts are managed by an existing admin, not this endpoint."""
    expected_token = get_settings().admin_bootstrap_token
    if not expected_token or not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise ForbiddenError("Jeton de bootstrap invalide ou non configuré.")

    if await repository.admin_exists(db):
        raise ConflictError("Un compte admin existe déjà.")
    if await repository.get_by_phone(db, data.phone) is not None:
        raise ConflictError("Ce numéro de téléphone est déjà utilisé.")
    if await repository.get_by_email(db, data.email) is not None:
        raise ConflictError("Cet email est déjà utilisé.")

    user = await repository.create(
        db,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.ADMIN,
        email=data.email,
    )
    user.email_verified = True  # trusted by the bootstrap secret, skip the OTP round-trip
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, data: LoginRequest) -> User:
    user = await repository.get_by_phone(db, data.phone)
    if user is None or not verify_password(data.password, user.password_hash):
        raise UnauthorizedError(INVALID_CREDENTIALS_MESSAGE)
    if not user.is_active:
        raise UnauthorizedError("Ce compte a été désactivé.")
    return user


def issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(str(user.id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token, TokenType.REFRESH)
        user_id = uuid.UUID(payload["sub"])
    except (InvalidTokenError, ValueError) as exc:
        raise UnauthorizedError("Jeton de rafraîchissement invalide ou expiré, veuillez vous reconnecter.") from exc

    user = await repository.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Compte introuvable ou désactivé.")

    return issue_tokens(user)


async def forgot_password(db: AsyncSession, phone: str) -> None:
    """Always a no-op from the caller's point of view — same response whether or not
    an account exists for this phone, so the endpoint can't be used to enumerate accounts."""
    user = await repository.get_by_phone(db, phone)
    if user is None or not user.email:
        return

    try:
        code = await user_service.create_code(db, user, EmailCodePurpose.PASSWORD_RESET)
    except ConflictError:
        # A code was already requested recently — resending would leak that this
        # phone number has an account in cooldown, so stay silent instead.
        return

    subject, text, html = password_reset_email(code, user_service.CODE_TTL_MINUTES)
    await send_email(user.email, subject, text, html)


async def reset_password(db: AsyncSession, phone: str, code: str, new_password: str) -> None:
    user = await repository.get_by_phone(db, phone)
    if user is None:
        raise ConflictError("Code invalide ou expiré.")

    await user_service.consume_code(db, user, EmailCodePurpose.PASSWORD_RESET, code)
    user.password_hash = hash_password(new_password)
    await db.commit()
