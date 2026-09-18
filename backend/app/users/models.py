"""User ORM model, role enum, and one-time email codes (verification, password reset)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class UserRole(StrEnum):
    BUYER = "buyer"
    VENDOR = "vendor"
    COURIER = "courier"
    PICKUP_POINT_MANAGER = "pickup_point_manager"
    ADMIN = "admin"


class EmailCodePurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    # Compte livreur créé directement par un admin (voir
    # app/couriers/service.py::admin_create_courier) — le livreur reçoit ce
    # code par email pour définir son mot de passe et prouver qu'il contrôle
    # bien cette adresse, avant de compléter lui-même son profil.
    COURIER_INVITATION = "courier_invitation"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", values_callable=lambda enum: [e.value for e in enum]),
        default=UserRole.BUYER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Email is mandatory and verified at registration (see
    # app/auth/service.py::register_user) — this starts False and flips once
    # the signup code is confirmed, same flow as vendor onboarding.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EmailCode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One active code per (user, purpose) — a new send (register/resend/forgot-password)
    replaces the previous one for that purpose.

    The code itself is short (4-5 digits, ~100k possibilities), so `attempts`
    caps guesses and `expires_at` bounds the window; both matter more here
    than they would for a long random token.
    """

    __tablename__ = "email_codes"
    __table_args__ = (UniqueConstraint("user_id", "purpose"),)

    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    purpose: Mapped[EmailCodePurpose] = mapped_column(
        SAEnum(EmailCodePurpose, name="email_code_purpose", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
