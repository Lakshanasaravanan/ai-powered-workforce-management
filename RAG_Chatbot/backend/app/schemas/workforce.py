"""Minimal, synthetic workforce contracts used by the Phase 4 mock provider."""

from __future__ import annotations

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
