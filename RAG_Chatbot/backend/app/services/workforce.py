"""Provider boundary with a deliberately synthetic, in-memory Phase 4 implementation."""

from __future__ import annotations

from typing import Protocol

from app.schemas.workforce import AttendancePeriod, AttendanceSummary, EmployeeProfile, LeaveBalance


class WorkforceProviderError(RuntimeError):
    """Safe provider failure; no backend implementation details are exposed."""


class WorkforceProvider(Protocol):
    def get_profile(self, employee_id: str) -> EmployeeProfile: ...

    def get_leave_balance(self, employee_id: str) -> LeaveBalance: ...

    def get_attendance_summary(self, employee_id: str, period: AttendancePeriod) -> AttendanceSummary: ...


class MockWorkforceProvider:
    """Synthetic fixture only. It performs no database, network, or SLAMS access."""

    _profiles = {
        "EMP001": EmployeeProfile(employee_id="EMP001", display_name="Avery Sample", department="Sample Operations", employment_type="Sample Full-time"),
        "EMP002": EmployeeProfile(employee_id="EMP002", display_name="Jordan Example", department="Sample People", employment_type="Sample Full-time"),
    }
    _leave_balances = {
        "EMP001": LeaveBalance(annual_days_remaining=12.0, sick_days_remaining=6.0),
        "EMP002": LeaveBalance(annual_days_remaining=9.0, sick_days_remaining=5.0),
    }

    def _require_known_employee(self, employee_id: str) -> None:
        if employee_id not in self._profiles:
            raise WorkforceProviderError("Synthetic workforce record is unavailable")

    def get_profile(self, employee_id: str) -> EmployeeProfile:
        self._require_known_employee(employee_id)
        return self._profiles[employee_id]

    def get_leave_balance(self, employee_id: str) -> LeaveBalance:
        self._require_known_employee(employee_id)
        return self._leave_balances[employee_id]

    def get_attendance_summary(self, employee_id: str, period: AttendancePeriod) -> AttendanceSummary:
        self._require_known_employee(employee_id)
        if period is AttendancePeriod.CURRENT_MONTH:
            return AttendanceSummary(period=period, scheduled_days=20, present_days=18, leave_days=2)
        return AttendanceSummary(period=period, scheduled_days=22, present_days=20, leave_days=2)
