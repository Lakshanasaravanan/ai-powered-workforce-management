"""Safe, read-only client for the SLAMS self-service API."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.schemas.workforce import AttendancePeriod, AttendanceSummary, AttendanceRecord, AttendanceRegularizationExecutionResponse, EmployeeProfile, LeaveBalance, LeaveExecutionResponse
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

class _SLAMSAttendance(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    date: date
    checkInTime: time | None = None
    checkOutTime: time | None = None
    status: str
    workingHours: float | None = None

class _SLAMSLeaveExecution(BaseModel):
    model_config = ConfigDict(extra="ignore")
    leaveRequestId: int; status: str; leaveType: str; startDate: date; endDate: date; appliedAt: datetime; idempotentReplay: bool

class _SLAMSRegularizationExecution(BaseModel):
    model_config = ConfigDict(extra="ignore")
    regularizationRequestId: int; attendanceId: int; requestedInTime: time; requestedOutTime: time | None = None; status: str; requestedAt: datetime; idempotentReplay: bool


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

    def post_json(self, path: str, employee_id: str, idempotency_key: str, payload: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._signer.sign(employee_id)}", "Idempotency-Key": idempotency_key}
        if request_id: headers["X-Request-ID"] = request_id
        response: httpx.Response | None = None
        for attempt in range(2):
            try: response = self._client.post(path, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 0: continue
                raise WorkforceUnavailable("Workforce service is temporarily unavailable") from exc
            if response.status_code not in self._TRANSIENT_STATUS_CODES or attempt == 1: break
        assert response is not None
        self._raise_for_status(response.status_code)
        try: body = response.json()
        except ValueError as exc: raise WorkforceContractError("Workforce service returned an invalid response") from exc
        if not isinstance(body, dict): raise WorkforceContractError("Workforce service returned an invalid response")
        return body

    def get_list(self, path: str, employee_id: str, request_id: str | None) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self._signer.sign(employee_id)}"}
        if request_id: headers["X-Request-ID"] = request_id
        response: httpx.Response | None = None
        for attempt in range(2):
            try: response = self._client.get(path, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 0: continue
                raise WorkforceUnavailable("Workforce service is temporarily unavailable") from exc
            if response.status_code not in self._TRANSIENT_STATUS_CODES or attempt == 1: break
        assert response is not None
        self._raise_for_status(response.status_code)
        try: payload = response.json()
        except ValueError as exc: raise WorkforceContractError("Workforce service returned an invalid response") from exc
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload): raise WorkforceContractError("Workforce service returned an invalid response")
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

    def get_attendance_records(self, employee_id: str, request_id: str | None = None) -> list[AttendanceRecord]:
        try: records = [_SLAMSAttendance.model_validate(item) for item in self._client.get_list("/api/attendance/my", employee_id, request_id)]
        except ValidationError as exc: raise WorkforceContractError("Workforce service returned an unexpected response") from exc
        return [AttendanceRecord(attendance_id=item.id, attendance_date=item.date, check_in_time=item.checkInTime, check_out_time=item.checkOutTime, status=item.status, working_hours=item.workingHours, synthetic_data=False) for item in records]

    def request_leave(self, employee_id: str, idempotency_key: str, leave_type: str, start_date: date, end_date: date, reason: str, request_id: str | None = None) -> LeaveExecutionResponse:
        result = self._validated(_SLAMSLeaveExecution, self._client.post_json("/api/leaves/apply", employee_id, idempotency_key, {"leaveType": leave_type, "startDate": start_date.isoformat(), "endDate": end_date.isoformat(), "reason": reason}, request_id))
        assert isinstance(result, _SLAMSLeaveExecution)
        return LeaveExecutionResponse(leave_request_id=result.leaveRequestId, status=result.status, leave_type=result.leaveType, start_date=result.startDate, end_date=result.endDate, applied_at=result.appliedAt, idempotent_replay=result.idempotentReplay)

    def regularize_attendance(self, employee_id: str, idempotency_key: str, attendance_id: int, requested_in_time: time, requested_out_time: time | None, reason: str, request_id: str | None = None) -> AttendanceRegularizationExecutionResponse:
        body = {"attendanceId": attendance_id, "requestedInTime": requested_in_time.isoformat(), "reason": reason}
        if requested_out_time is not None: body["requestedOutTime"] = requested_out_time.isoformat()
        result = self._validated(_SLAMSRegularizationExecution, self._client.post_json("/api/attendance/regularize", employee_id, idempotency_key, body, request_id))
        assert isinstance(result, _SLAMSRegularizationExecution)
        return AttendanceRegularizationExecutionResponse(regularization_request_id=result.regularizationRequestId, attendance_id=result.attendanceId, requested_in_time=result.requestedInTime, requested_out_time=result.requestedOutTime, status=result.status, requested_at=result.requestedAt, idempotent_replay=result.idempotentReplay)
