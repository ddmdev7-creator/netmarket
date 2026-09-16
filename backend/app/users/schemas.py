"""Pydantic schemas for the user profile."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.users.models import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    first_name: str | None
    last_name: str | None
    email: str | None
    email_verified: bool
    role: UserRole
    is_active: bool


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: str | None = None


class VerifyEmailRequest(BaseModel):
    code: str = Field(pattern=r"^\d{4,5}$")


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=8)
