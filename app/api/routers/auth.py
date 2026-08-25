"""Authentication endpoints: registration and login.

Passwords are stored as bcrypt hashes. Login verifies the password and issues
a signed JWT access token. No roles/permissions are handled here — that is a
later authorization phase.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.dependencies import get_session
from app.api.schemas.auth import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    TeamMemberInfo,
    TokenResponse,
    UserResponse,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.models import TeamMember, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        role=user.role,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    session: Annotated[Session, Depends(get_session)],
) -> UserResponse:
    """Create a new user account with a securely hashed password."""
    existing = session.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an account with this email already exists",
        )

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        # Concurrent registration for the same email between the pre-check and
        # commit; the unique constraint on users.email is the safety net.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an account with this email already exists",
        ) from exc
    session.refresh(user)
    return _user_response(user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    """Verify credentials and return a JWT access token."""
    user = session.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()

    # Same generic message for unknown email / wrong password so the endpoint
    # does not reveal which accounts exist.
    if (
        user is None
        or not verify_password(payload.password, user.hashed_password)
        or not user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=MeResponse)
def me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    """Return the authenticated user's profile plus their mapped team member.

    ``member`` is populated when the account is linked to a firm/team member
    (``users.member_id``); self-registered accounts return ``member=None``.
    """
    member = None
    if current_user.member_id is not None:
        row = session.get(TeamMember, current_user.member_id)
        if row is not None:
            member = TeamMemberInfo(
                member_id=row.member_id,
                name=row.name,
                role=row.role,
                practice=row.practice,
                can_approve=row.can_approve,
            )
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        member_id=current_user.member_id,
        member=member,
    )
