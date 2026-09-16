"""Routes for the authenticated user's own profile, plus admin account management."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import Message
from app.core.deps import get_current_user, get_db, require_role
from app.users import service
from app.users.models import User, UserRole
from app.users.schemas import AdminPasswordReset, UserRead, UserUpdate, VerifyEmailRequest

router = APIRouter(prefix="/users", tags=["users"])
admin_router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.get("/me", response_model=UserRead)
async def read_my_profile(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await service.update_profile(db, current_user, payload)


@router.post("/me/resend-verification-email", response_model=Message)
async def resend_verification_email(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Message:
    await service.send_verification_code(db, current_user)
    return Message(detail="Code envoyé.")


@router.post("/me/verify-email", response_model=UserRead)
async def verify_email(
    payload: VerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await service.verify_email_code(db, current_user, payload.code)


@admin_router.get("", response_model=list[UserRead])
async def admin_list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    return await service.admin_list_users(db)


@admin_router.delete("/{user_id}", response_model=Message)
async def admin_delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Message:
    await service.admin_delete_user(db, current_user, user_id)
    return Message(detail="Compte supprimé.")


@admin_router.patch("/{user_id}/password", response_model=Message)
async def admin_reset_password(
    user_id: uuid.UUID,
    payload: AdminPasswordReset,
    db: AsyncSession = Depends(get_db),
) -> Message:
    await service.admin_reset_password(db, user_id, payload)
    return Message(detail="Mot de passe réinitialisé.")
