"""Reusable authentication dependencies for FastAPI routes.

Usage on a route that requires an authenticated user::

    @router.get("/me")
    def me(current_user: User = Depends(get_current_user)) -> User:
        return current_user
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.core.security import AuthError, decode_access_token
from app.models import User

# auto_error=False lets us return a clean 401 instead of FastAPI's default 403.
_bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _extract_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _CREDENTIALS_EXCEPTION
    return credentials.credentials


def get_current_user(
    token: Annotated[str, Depends(_extract_token)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """Verify the JWT from ``Authorization: Bearer <token>`` and load the user."""
    try:
        payload = decode_access_token(token)
    except AuthError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    subject = str(payload["sub"])
    if not subject.isdigit():
        raise _CREDENTIALS_EXCEPTION

    user = session.get(User, int(subject))
    if user is None or not user.is_active:
        # Unknown or deactivated account invalidates previously issued tokens.
        raise _CREDENTIALS_EXCEPTION
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

_FORBIDDEN_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="you do not have permission to perform this action",
)


def require_admin(current_user: CurrentUser) -> User:
    """Authorization dependency: the authenticated user must be an ``admin``.

    Authentication (``get_current_user``) answers *who the user is*; this
    dependency answers *what the user may do*. Raises 403 (not 401) because
    the request is authenticated but lacks permission.
    """
    if current_user.role != "admin":
        raise _FORBIDDEN_EXCEPTION
    return current_user
