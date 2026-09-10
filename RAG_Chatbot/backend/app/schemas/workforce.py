"""Minimal, synthetic workforce contracts used by the Phase 4 mock provider."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AttendancePeriod(StrEnum):
    CURRENT_MONTH = "current_month"
    LAST_30_DAYS = "last_30_days"


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    employee_id: str
    display_name: str
    department: str
    employment_type: str
    synthetic_data: bool = True


class LeaveBalance(BaseModel):
    model_config = ConfigDict(frozen=True)

    annual_days_remaining: float = Field(ge=0)
    sick_days_remaining: float = Field(ge=0)
    synthetic_data: bool = True


class AttendanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: AttendancePeriod
    scheduled_days: int = Field(ge=0)
    present_days: int = Field(ge=0)
    leave_days: int = Field(ge=0)
    synthetic_data: bool = True
