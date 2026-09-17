"""Registration, login, token refresh and self-service password reset endpoints."""

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import (
    AdminBootstrapRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
)
from app.common.schemas import Message
from app.core.deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await service.register_user(db, payload)
    return service.issue_tokens(user)


@router.post("/admin-bootstrap", response_model=Message, status_code=status.HTTP_201_CREATED)
async def admin_bootstrap(
    payload: AdminBootstrapRequest,
    x_bootstrap_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Message:
    await service.bootstrap_admin(db, payload, provided_token=x_bootstrap_token)
    return Message(detail="Compte admin créé. Connecte-toi via /auth/login.")


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await service.authenticate_user(db, payload)
    return service.issue_tokens(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    return await service.refresh_tokens(db, payload.refresh_token)


@router.post("/forgot-password", response_model=Message)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> Message:
    await service.forgot_password(db, payload.phone)
    return Message(detail="Si un compte existe avec ce numéro et un email associé, un code a été envoyé.")


@router.post("/reset-password", response_model=Message)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> Message:
    await service.reset_password(db, payload.phone, payload.code, payload.new_password)
    return Message(detail="Mot de passe réinitialisé.")
