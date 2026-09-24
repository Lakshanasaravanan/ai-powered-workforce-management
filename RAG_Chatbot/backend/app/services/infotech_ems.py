"""Fixed, read-only EMS API client for InfoTech agent tools.

The client intentionally exposes no generic HTTP method or caller-controlled
path.  The EMS base URL is trusted backend configuration and bearer tokens are
accepted only as request-lifetime transport credentials.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings


class EMSReadClientError(RuntimeError):
    """Safe base error for a read-only EMS operation."""


class EMSUnauthorized(EMSReadClientError):
    pass


class EMSForbidden(EMSReadClientError):
    pass


class EMSNotFound(EMSReadClientError):
    pass


class EMSConflict(EMSReadClientError):
    pass


class EMSValidationFailure(EMSReadClientError):
    pass


class EMSRateLimited(EMSReadClientError):
    pass


class EMSUnavailable(EMSReadClientError):
    pass


class EMSContractError(EMSReadClientError):
    pass

class EMSUncertainOutcome(EMSReadClientError):
    """Transport/5xx result where EMS may have committed the request."""


class EMSProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    employee_code: str = Field(min_length=1, max_length=32)
    full_name: str = Field(min_length=1, max_length=120)
    company_email: str = Field(min_length=1, max_length=255)
    role: Literal["ADMIN", "MANAGER", "EMPLOYEE"]
    designation: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)
    manager_id: UUID | None
    is_active: bool


class EMSManagerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manager: EMSProfile | None


class EMSLeaveEmployee(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    employee_code: str
    full_name: str


class EMSLeave(BaseModel):
    """The safe subset of the established EMS leave response contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    employee: EMSLeaveEmployee
    leave_type: Literal["CASUAL", "MEDICAL", "EMERGENCY", "DAY_OFF"]
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    start_date: date
    end_date: date
    duration: Literal["FULL_DAY", "HALF_DAY"]
    half_day_period: Literal["MORNING", "AFTERNOON"] | None
    reason: str = Field(min_length=1, max_length=1000)
    approval_required: bool
    decided_by_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    decision_source: Literal["AUTOMATIC_POLICY", "MANAGER"] | None
    manager_notification_delivered: bool | None = None
    created_at: datetime
    updated_at: datetime


class EMSNotification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    category: Literal["LEAVE", "CHAT", "CALENDAR", "SYSTEM"]
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=1000)
    is_read: bool
    read_at: datetime | None
    related_entity_type: str | None
    related_entity_id: UUID | None
    created_at: datetime


class EMSUnreadCount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unread_count: int = Field(ge=0)


class InfoTechEMSReadClient:
    """Explicit EMS reads only; no mutation or arbitrary-path surface exists."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if settings.ems_api_base_url is None:
            raise EMSUnavailable("InfoTech EMS is not configured")
        self._base_url = str(settings.ems_api_base_url).rstrip("/")
        self._timeout = settings.ems_auth_timeout_seconds
        self._client = client

    def _get(self, path: str, bearer_token: str) -> object:
        try:
            if self._client is not None:
                response = self._client.get(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {bearer_token}"},
                    timeout=self._timeout,
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(
                        f"{self._base_url}{path}",
                        headers={"Authorization": f"Bearer {bearer_token}"},
                    )
        except httpx.TimeoutException as exc:
            raise EMSUnavailable("InfoTech EMS is temporarily unavailable") from exc
        except httpx.HTTPError as exc:
            raise EMSUnavailable("InfoTech EMS is temporarily unavailable") from exc
        status = response.status_code
        if status == 401:
            raise EMSUnauthorized("EMS authentication is no longer valid")
        if status == 403:
            raise EMSForbidden("EMS denied this operation")
        if status == 404:
            raise EMSNotFound("EMS record is unavailable")
        if status == 409:
            raise EMSConflict("EMS request conflicts with current state")
        if status == 422:
            raise EMSValidationFailure("EMS rejected the request")
        if status == 429:
            raise EMSRateLimited("EMS is temporarily rate limited")
        if status < 200 or status >= 300:
            raise EMSUnavailable("InfoTech EMS is temporarily unavailable")
        try:
            return response.json()
        except ValueError as exc:
            raise EMSContractError("EMS returned an invalid response") from exc

    @staticmethod
    def _parse(model: type[BaseModel], payload: object):
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise EMSContractError("EMS returned an invalid response") from exc

    def get_my_profile(self, bearer_token: str) -> EMSProfile:
        return self._parse(EMSProfile, self._get("/api/v1/auth/me", bearer_token))

    def get_my_manager(self, bearer_token: str) -> EMSManagerResult:
        return self._parse(EMSManagerResult, self._get("/api/v1/employees/me/manager", bearer_token))

    def get_my_leaves(self, bearer_token: str) -> list[EMSLeave]:
        payload = self._get("/api/v1/leaves/me", bearer_token)
        if not isinstance(payload, list):
            raise EMSContractError("EMS returned an invalid response")
        return [self._parse(EMSLeave, item) for item in payload]

    def get_my_notifications(self, bearer_token: str) -> list[EMSNotification]:
        payload = self._get("/api/v1/notifications", bearer_token)
        if not isinstance(payload, list):
            raise EMSContractError("EMS returned an invalid response")
        return [self._parse(EMSNotification, item) for item in payload]

    def get_unread_notification_count(self, bearer_token: str) -> EMSUnreadCount:
        return self._parse(EMSUnreadCount, self._get("/api/v1/notifications/unread-count", bearer_token))

    def get_direct_reports(self, bearer_token: str) -> list[EMSProfile]:
        payload = self._get("/api/v1/employees/me/direct-reports", bearer_token)
        if not isinstance(payload, list):
            raise EMSContractError("EMS returned an invalid response")
        return [self._parse(EMSProfile, item) for item in payload]

    def get_team_leaves(self, bearer_token: str) -> list[EMSLeave]:
        payload = self._get("/api/v1/leaves/team", bearer_token)
        if not isinstance(payload, list):
            raise EMSContractError("EMS returned an invalid response")
        return [self._parse(EMSLeave, item) for item in payload]

    def get_leave(self, leave_id: UUID, bearer_token: str) -> EMSLeave:
        """Fixed exact-ID read used internally to preflight a stored decision target."""
        return self._parse(EMSLeave, self._get(f"/api/v1/leaves/{leave_id}", bearer_token))

    def apply_leave(self, leave: object, bearer_token: str, idempotency_key: str, correlation_id: str | None) -> EMSLeave:
        """Only consequential operation exposed by this client; endpoint is fixed."""
        payload = leave.model_dump(mode="json")
        headers = {"Authorization": f"Bearer {bearer_token}", "Idempotency-Key": idempotency_key, "X-InfoTech-Agent": "1"}
        if correlation_id:
            headers["X-Request-ID"] = correlation_id
        try:
            if self._client is not None:
                response = self._client.post(f"{self._base_url}/api/v1/leaves", json=payload, headers=headers, timeout=self._timeout)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(f"{self._base_url}/api/v1/leaves", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EMSUncertainOutcome("EMS outcome is pending safe recovery") from exc
        if response.status_code >= 500:
            raise EMSUncertainOutcome("EMS outcome is pending safe recovery")
        if response.status_code == 401: raise EMSUnauthorized("EMS authentication is no longer valid")
        if response.status_code == 403: raise EMSForbidden("EMS denied this operation")
        if response.status_code == 409: raise EMSConflict("EMS request conflicts with current state")
        if response.status_code in {400, 422}: raise EMSValidationFailure("EMS rejected the request")
        if response.status_code < 200 or response.status_code >= 300: raise EMSUnavailable("InfoTech EMS is temporarily unavailable")
        try: return self._parse(EMSLeave, response.json())
        except ValueError as exc: raise EMSContractError("EMS returned an invalid response") from exc

    def _decide_leave(self, leave: object, operation: Literal["approve", "reject"], bearer_token: str, idempotency_key: str, correlation_id: str | None) -> EMSLeave:
        """Fixed manager-decision transport; callers cannot select arbitrary paths."""
        leave_id = getattr(leave, "leave_id", None)
        if not isinstance(leave_id, UUID):
            raise EMSContractError("Stored leave decision is invalid")
        payload = {"decision_note": getattr(leave, "decision_note", None)}
        headers = {"Authorization": f"Bearer {bearer_token}", "Idempotency-Key": idempotency_key, "X-InfoTech-Agent": "1"}
        if correlation_id:
            headers["X-Request-ID"] = correlation_id
        try:
            if self._client is not None:
                response = self._client.post(f"{self._base_url}/api/v1/leaves/{leave_id}/{operation}", json=payload, headers=headers, timeout=self._timeout)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(f"{self._base_url}/api/v1/leaves/{leave_id}/{operation}", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EMSUncertainOutcome("EMS outcome is pending safe recovery") from exc
        if response.status_code >= 500: raise EMSUncertainOutcome("EMS outcome is pending safe recovery")
        if response.status_code == 401: raise EMSUnauthorized("EMS authentication is no longer valid")
        if response.status_code == 403: raise EMSForbidden("EMS denied this operation")
        if response.status_code == 409: raise EMSConflict("EMS request conflicts with current state")
        if response.status_code in {400, 422}: raise EMSValidationFailure("EMS rejected the request")
        if response.status_code < 200 or response.status_code >= 300: raise EMSUnavailable("InfoTech EMS is temporarily unavailable")
        try: return self._parse(EMSLeave, response.json())
        except ValueError as exc: raise EMSContractError("EMS returned an invalid response") from exc

    def approve_leave(self, leave: object, bearer_token: str, idempotency_key: str, correlation_id: str | None) -> EMSLeave:
        return self._decide_leave(leave, "approve", bearer_token, idempotency_key, correlation_id)

    def reject_leave(self, leave: object, bearer_token: str, idempotency_key: str, correlation_id: str | None) -> EMSLeave:
        return self._decide_leave(leave, "reject", bearer_token, idempotency_key, correlation_id)
