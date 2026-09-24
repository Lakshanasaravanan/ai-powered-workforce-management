"""Verification boundary for InfoTech EMS-issued access tokens.

The EMS token currently carries only a UUID subject and expiry.  This module
therefore verifies its HS256 signature locally and then asks EMS ``/auth/me``
for the current, active employee identity.  It never accesses EMS storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
import jwt
from jwt import InvalidTokenError

from app.core.config import Settings


class EMSIdentityError(RuntimeError):
    """A token or the authoritative EMS identity response was unacceptable."""


class EMSIdentityUnavailable(RuntimeError):
    """The configured EMS identity service could not be reached safely."""


@dataclass(frozen=True, slots=True)
class EMSIdentity:
    employee_id: UUID
    employee_code: str
    display_name: str
    role: str


class EMSIdentityVerifier:
    """Validate an EMS access token and resolve its current employee identity."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._secret = settings.ems_jwt_secret.get_secret_value() if settings.ems_jwt_secret else None
        self._algorithm = settings.ems_jwt_algorithm
        self._base_url = str(settings.ems_api_base_url).rstrip("/") if settings.ems_api_base_url else None
        self._timeout = settings.ems_auth_timeout_seconds
        self._client = client

    def _decode_subject(self, token: str) -> UUID:
        if not self._secret:
            raise EMSIdentityUnavailable("InfoTech identity verification is not configured")
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["sub", "exp"]},
            )
            return UUID(claims["sub"])
        except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise EMSIdentityError("Invalid or expired EMS access token") from exc

    def authenticate(self, token: str) -> EMSIdentity:
        subject = self._decode_subject(token)
        if not self._base_url:
            raise EMSIdentityUnavailable("InfoTech identity verification is not configured")
        try:
            if self._client is not None:
                response = self._client.get(
                    f"{self._base_url}/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(
                        f"{self._base_url}/api/v1/auth/me",
                        headers={"Authorization": f"Bearer {token}"},
                    )
        except httpx.HTTPError as exc:
            raise EMSIdentityUnavailable("InfoTech identity verification is unavailable") from exc
        if response.status_code in {401, 403}:
            raise EMSIdentityError("EMS access token is no longer valid")
        if response.status_code != 200:
            raise EMSIdentityUnavailable("InfoTech identity verification is unavailable")
        try:
            payload = response.json()
            employee_id = UUID(payload["id"])
            employee_code = payload["employee_code"]
            display_name = payload["full_name"]
            role = payload["role"]
            active = payload["is_active"]
        except (ValueError, KeyError, TypeError) as exc:
            raise EMSIdentityUnavailable("InfoTech identity response is invalid") from exc
        if (
            employee_id != subject
            or not isinstance(employee_code, str)
            or not employee_code
            or not isinstance(display_name, str)
            or not display_name
            or role not in {"ADMIN", "MANAGER", "EMPLOYEE"}
            or active is not True
        ):
            raise EMSIdentityError("EMS identity response is not authorized")
        return EMSIdentity(employee_id, employee_code, display_name, role)
