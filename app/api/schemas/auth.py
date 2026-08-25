"""Pydantic schemas for the /auth endpoints."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Simple RFC-5322-ish shape check. ``pydantic.EmailStr`` would require the
# optional ``email-validator`` package; this keeps the dependency surface
# minimal while still rejecting obviously malformed addresses.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_PATTERN.match(normalized):
        raise ValueError("value is not a valid email address")
    return normalized


class RegisterRequest(BaseModel):
    """Payload for POST /auth/register."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    _normalize_email = field_validator("email")(_validate_email)


class LoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    _normalize_email = field_validator("email")(_validate_email)


class UserResponse(BaseModel):
    """Public representation of a user (never exposes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    role: str = "member"
    created_at: str | None = None


class TeamMemberInfo(BaseModel):
    """Public representation of the firm/team member an account maps to."""

    model_config = ConfigDict(from_attributes=True)

    member_id: str
    name: str
    role: str
    practice: str | None = None
    can_approve: bool = False


class MeResponse(BaseModel):
    """Profile of the authenticated user, including their mapped team member."""

    id: int
    email: str
    role: str
    is_active: bool
    member_id: str | None = None
    member: TeamMemberInfo | None = None


class TokenResponse(BaseModel):
    """JWT access token returned by POST /auth/login."""

    access_token: str
    token_type: str = "bearer"
