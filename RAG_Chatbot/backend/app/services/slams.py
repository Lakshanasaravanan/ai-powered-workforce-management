"""Safe, read-only client for the SLAMS self-service API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.schemas.workforce import AttendancePeriod, AttendanceSummary, EmployeeProfile, LeaveBalance
from app.services.workforce import (
    WorkforceBusinessError,
    WorkforceContractError,
    WorkforceForbidden,
    WorkforceNotFound,
    WorkforceProviderError,
    WorkforceUnauthorized,
    WorkforceUnavailable,
)


class DelegationTokenSigner:
    """Create short-lived RS256 delegation tokens for a server-bound employee."""

    def __init__(self, issuer: str, audience: str, private_key: str, ttl_seconds: int) -> None:
        self._issuer = issuer
        self._audience = audience
        self._private_key = private_key
        self._ttl_seconds = ttl_seconds

    def sign(self, employee_id: str) -> str:
        now = datetime.now(UTC)
        claims = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": employee_id,
            "employee_id": employee_id,
            "iat": now,
            "exp": now + timedelta(seconds=self._ttl_seconds),
            "jti": str(uuid4()),
            "token_type": "delegation",
        }
        return jwt.encode(claims, self._private_key, algorithm="RS256")


class _SLAMSProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    employeeId: str
    fullName: str
    department: str | None = None
    designation: str | None = None


class _SLAMSLeaveBalance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    casualLeave: int
    sickLeave: int
    earnedLeave: int


class _SLAMSAttendanceAnalytics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attendancePercentage: float
    presentCount: int
    lateCount: int
    halfDayCount: int
    absentCount: int
    totalDays: int


class SLAMSClient:
    """Reusable synchronous HTTP client with safe failures and bounded read retries."""

    _TRANSIENT_STATUS_CODES = {502, 503, 504}

    def __init__(self, base_url: str, signer: DelegationTokenSigner, connect_timeout: float, read_timeout: float, client: httpx.Client | None = None) -> None:
        self._signer = signer
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=read_timeout, pool=connect_timeout),
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_json(self, path: str, employee_id: str, request_id: str | None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._signer.sign(employee_id)}"}
        if request_id:
            headers["X-Request-ID"] = request_id

        response: httpx.Response | None = None
        for attempt in range(2):
            try:
                response = self._client.get(path, headers=headers)
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    continue
                raise WorkforceUnavailable("Workforce service is temporarily unavailable") from exc
            except httpx.TransportError as exc:
                if attempt == 0:
                    continue
                raise WorkforceUnavailable("Workforce service is temporarily unavailable") from exc
            if response.status_code not in self._TRANSIENT_STATUS_CODES or attempt == 1:
                break

        assert response is not None
        self._raise_for_status(response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise WorkforceContractError("Workforce service returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise WorkforceContractError("Workforce service returned an invalid response")
        return payload

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        if status_code == 401:
            raise WorkforceUnauthorized("Workforce authentication failed")
        if status_code == 403:
            raise WorkforceForbidden("Workforce authorization failed")
        if status_code == 404:
            raise WorkforceNotFound("Workforce record is unavailable")
        if status_code in {400, 409}:
            raise WorkforceBusinessError("Workforce request could not be completed")
        raise WorkforceUnavailable("Workforce service is temporarily unavailable")


class SLAMSWorkforceProvider:
    """Maps SLAMS principal-bound read endpoints to the workforce provider contract."""

    def __init__(self, client: SLAMSClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> "SLAMSWorkforceProvider":
        assert settings.slams_base_url is not None
        assert settings.slams_delegation_issuer is not None
        assert settings.slams_delegation_audience is not None
        assert settings.slams_delegation_private_key is not None
        signer = DelegationTokenSigner(
            settings.slams_delegation_issuer,
            settings.slams_delegation_audience,
            settings.slams_delegation_private_key.get_secret_value(),
            settings.slams_delegation_token_ttl_seconds,
        )
        return cls(SLAMSClient(
            str(settings.slams_base_url), signer, settings.slams_connect_timeout_seconds, settings.slams_read_timeout_seconds,
        ))

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _validated(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise WorkforceContractError("Workforce service returned an unexpected response") from exc

    def get_profile(self, employee_id: str, request_id: str | None = None) -> EmployeeProfile:
        profile = self._validated(_SLAMSProfile, self._client.get_json("/api/employees/me", employee_id, request_id))
        assert isinstance(profile, _SLAMSProfile)
        if profile.employeeId != employee_id:
            raise WorkforceContractError("Workforce service returned an unexpected employee")
        return EmployeeProfile(
            employee_id=profile.employeeId,
            display_name=profile.fullName,
            department=profile.department,
            designation=profile.designation,
            employment_type=None,
            synthetic_data=False,
        )

    def get_leave_balance(self, employee_id: str, request_id: str | None = None) -> LeaveBalance:
        balance = self._validated(_SLAMSLeaveBalance, self._client.get_json("/api/leaves/balance", employee_id, request_id))
        assert isinstance(balance, _SLAMSLeaveBalance)
        return LeaveBalance(
            annual_days_remaining=float(balance.casualLeave + balance.earnedLeave),
            sick_days_remaining=float(balance.sickLeave),
            casual_days_remaining=float(balance.casualLeave),
            earned_days_remaining=float(balance.earnedLeave),
            synthetic_data=False,
        )

    def get_attendance_summary(self, employee_id: str, period: AttendancePeriod, request_id: str | None = None) -> AttendanceSummary:
        if period is not AttendancePeriod.SLAMS_AGGREGATE:
            raise WorkforceBusinessError("The requested attendance period is not supported by the workforce service")
        analytics = self._validated(_SLAMSAttendanceAnalytics, self._client.get_json("/api/attendance/analytics", employee_id, request_id))
        assert isinstance(analytics, _SLAMSAttendanceAnalytics)
        # SLAMS exposes aggregate analytics only; it does not label absences as leave.
        return AttendanceSummary(
            period=period,
            scheduled_days=analytics.totalDays,
            present_days=analytics.presentCount,
            leave_days=0,
            late_days=analytics.lateCount,
            half_days=analytics.halfDayCount,
            absent_days=analytics.absentCount,
            synthetic_data=False,
        )
