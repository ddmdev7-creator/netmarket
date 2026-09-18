"""Request/response schemas for registration, login and token refresh."""

from pydantic import BaseModel, EmailStr, Field

PHONE_PATTERN = r"^\+224\d{9}$"


class RegisterRequest(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN, description="Format international, ex: +224621234567")
    password: str = Field(min_length=8)
    email: EmailStr


class LoginRequest(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN)
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN)


class ResetPasswordRequest(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN)
    code: str = Field(pattern=r"^\d{4,5}$")
    new_password: str = Field(min_length=8)


class AcceptCourierInvitationRequest(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN)
    code: str = Field(pattern=r"^\d{4,5}$")
    new_password: str = Field(min_length=8)


class AdminBootstrapRequest(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN, description="Format international, ex: +224621234567")
    password: str = Field(min_length=8)
    email: EmailStr


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
