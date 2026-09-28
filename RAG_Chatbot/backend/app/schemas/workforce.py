"""Minimal, synthetic workforce contracts used by the Phase 4 mock provider."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AttendancePeriod(StrEnum):
    SLAMS_AGGREGATE = "slams_aggregate"
    CURRENT_MONTH = "current_month"
    LAST_30_DAYS = "last_30_days"


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    employee_id: str
    display_name: str
    department: str | None = None
    employment_type: str | None = None
    designation: str | None = None
    synthetic_data: bool = True


class LeaveBalance(BaseModel):
    model_config = ConfigDict(frozen=True)

    annual_days_remaining: float = Field(ge=0)
    sick_days_remaining: float = Field(ge=0)
    casual_days_remaining: float | None = Field(default=None, ge=0)
    earned_days_remaining: float | None = Field(default=None, ge=0)
    synthetic_data: bool = True


class AttendanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: AttendancePeriod
    scheduled_days: int = Field(ge=0)
    present_days: int = Field(ge=0)
    leave_days: int = Field(ge=0)
    late_days: int = Field(default=0, ge=0)
    half_days: int = Field(default=0, ge=0)
    absent_days: int = Field(default=0, ge=0)
    synthetic_data: bool = True


class AttendanceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    attendance_id: int = Field(gt=0)
    attendance_date: date
    check_in_time: time | None = None
    check_out_time: time | None = None
    status: str = Field(min_length=1, max_length=40)
    working_hours: float | None = None
    synthetic_data: bool = True


class LeaveExecutionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    leave_request_id: int = Field(gt=0)
    status: str
    leave_type: str
    start_date: date
    end_date: date
    applied_at: datetime
    idempotent_replay: bool


class AttendanceRegularizationExecutionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    regularization_request_id: int = Field(gt=0)
    attendance_id: int = Field(gt=0)
    requested_in_time: time
    requested_out_time: time | None = None
    status: str
    requested_at: datetime
    idempotent_replay: bool
