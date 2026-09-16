"""Bounded deterministic parsing for the single enabled future action."""
from __future__ import annotations
import re
from datetime import date, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApplyLeaveInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    leave_type: Literal["CASUAL", "MEDICAL", "EMERGENCY", "DAY_OFF"]
    start_date: date
    end_date: date
    duration: Literal["FULL_DAY", "HALF_DAY"]
    half_day_period: Literal["MORNING", "AFTERNOON"] | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def shape(self):
        if self.leave_type == "DAY_OFF":
            if self.duration != "HALF_DAY" or self.half_day_period is None or self.start_date != self.end_date:
                raise ValueError("DAY_OFF requires one MORNING or AFTERNOON half day")
        elif self.duration != "FULL_DAY" or self.half_day_period is not None:
            raise ValueError("non-DAY_OFF leave requires a full day")
        return self


def parse_apply_leave(message: str, today: date | None = None) -> tuple[ApplyLeaveInput | None, str | None]:
    text = " ".join(message.lower().split())
    leave_type = next((kind for kind in ("casual", "medical", "emergency") if f"{kind} leave" in text), None)
    if "day off" in text:
        leave_type = "day_off"
    if leave_type is None:
        return None, "Please specify leave type (Casual, Medical, Emergency, or Day Off) and a reason."
    if "tomorrow" not in text:
        return None, "Please provide an explicit date or say tomorrow; ambiguous dates are not guessed."
    reason = re.search(r"\bbecause\s+(.+?)[.!]?$", message.strip(), re.IGNORECASE)
    if not reason or not reason.group(1).strip():
        return None, "Please provide a reason for this leave request."
    resolved = (today or date.today()) + timedelta(days=1)
    if leave_type == "day_off":
        period = "MORNING" if "morning" in text else "AFTERNOON" if "afternoon" in text else None
        if period is None:
            return None, "Please specify whether the Day Off is for the morning or afternoon."
        return ApplyLeaveInput(leave_type="DAY_OFF", start_date=resolved, end_date=resolved, duration="HALF_DAY", half_day_period=period, reason=reason.group(1).strip()), None
    return ApplyLeaveInput(leave_type=leave_type.upper(), start_date=resolved, end_date=resolved, duration="FULL_DAY", reason=reason.group(1).strip()), None
