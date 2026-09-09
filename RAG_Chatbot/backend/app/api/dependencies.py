from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import AuthenticatedUser, decode_access_token


bearer_scheme = HTTPBearer(auto_error=True)
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    settings: SettingsDependency,
) -> AuthenticatedUser:
    """Derive identity solely from a verified bearer token."""
    return decode_access_token(credentials.credentials, settings)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
