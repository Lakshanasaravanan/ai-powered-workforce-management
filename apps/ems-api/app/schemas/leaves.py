from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.leave import (
    DecisionSource,
    HalfDayPeriod,
    LeaveDuration,
    LeaveStatus,
    LeaveType,
)


class LeaveCreate(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    duration: LeaveDuration
    half_day_period: HalfDayPeriod | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_dates_and_duration(self) -> "LeaveCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.leave_type is LeaveType.DAY_OFF:
            if self.duration is not LeaveDuration.HALF_DAY:
                raise ValueError("DAY_OFF requires HALF_DAY duration")
            if self.start_date != self.end_date:
                raise ValueError("DAY_OFF must be contained within one date")
            if self.half_day_period is None:
                raise ValueError("DAY_OFF requires half_day_period")
        elif self.duration is not LeaveDuration.FULL_DAY or self.half_day_period is not None:
            raise ValueError("non-DAY_OFF leave requires FULL_DAY duration without half_day_period")
        return self


class EmployeeSummary(BaseModel):
    id: UUID
    employee_code: str
    full_name: str


class LeaveDecision(BaseModel):
    decision_note: str | None = Field(default=None, max_length=1000)


class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee: EmployeeSummary
    leave_type: LeaveType
    status: LeaveStatus
    start_date: date
    end_date: date
    duration: LeaveDuration
    half_day_period: HalfDayPeriod | None
    reason: str
    approval_required: bool
    decided_by_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    decision_source: DecisionSource | None
    manager_notification_delivered: bool | None = None
    created_at: datetime
    updated_at: datetime
