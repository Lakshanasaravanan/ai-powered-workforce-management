from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import AuthenticatedUser, decode_access_token
from app.core.ems_auth import EMSIdentity, EMSIdentityError, EMSIdentityUnavailable


bearer_scheme = HTTPBearer(auto_error=True)
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    settings: SettingsDependency,
) -> AuthenticatedUser:
    """Derive identity solely from a verified bearer token."""
    return decode_access_token(credentials.credentials, settings)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def get_rag_service(request: Request):
    return request.app.state.rag_service


RAGServiceDependency = Annotated[object, Depends(get_rag_service)]


def get_agent_service(request: Request):
    return request.app.state.agent_service


AgentServiceDependency = Annotated[object, Depends(get_agent_service)]


def get_infotech_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> EMSIdentity:
    """Build identity solely from an EMS-issued bearer token and ``/auth/me``."""
    try:
        return request.app.state.ems_identity_verifier.authenticate(credentials.credentials)
    except EMSIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired EMS access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except EMSIdentityUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="InfoTech identity verification is temporarily unavailable",
        ) from exc


InfoTechIdentity = Annotated[EMSIdentity, Depends(get_infotech_identity)]
