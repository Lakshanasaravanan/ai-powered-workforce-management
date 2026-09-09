"""Development JWT identity boundary; replaceable by organization SSO later."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from app.core.config import Settings


@dataclass(frozen=True)
class AuthenticatedUser:
    employee_id: str
    display_name: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class MockUser:
    employee_id: str
    display_name: str
    password: str
    roles: tuple[str, ...]


MOCK_USERS: dict[str, MockUser] = {
    "EMP001": MockUser("EMP001", "Alex Employee", "demo-emp001", ("employee",)),
    "EMP002": MockUser("EMP002", "Blair Employee", "demo-emp002", ("employee",)),
}


def authenticate_mock_user(username: str, password: str) -> AuthenticatedUser | None:
    """Authenticate a development-only mock user without emitting credential logs."""
    user = MOCK_USERS.get(username.upper())
    if user is None or password != user.password:
        return None
    return AuthenticatedUser(user.employee_id, user.display_name, user.roles)


def create_access_token(user: AuthenticatedUser, settings: Settings) -> tuple[str, int]:
    expires_in = settings.jwt_access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.employee_id,
        "name": user.display_name,
        "roles": list(user.roles),
        "exp": now + timedelta(seconds=expires_in),
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm), expires_in


def decode_access_token(token: str, settings: Settings) -> AuthenticatedUser:
    try:
        payload = jwt.decode(token, settings.jwt_signing_key, algorithms=[settings.jwt_algorithm])
        employee_id, name, roles = payload.get("sub"), payload.get("name"), payload.get("roles")
        if not isinstance(employee_id, str) or not isinstance(name, str) or not isinstance(roles, list):
            raise InvalidTokenError("Token claims are incomplete")
        return AuthenticatedUser(employee_id, name, tuple(map(str, roles)))
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
