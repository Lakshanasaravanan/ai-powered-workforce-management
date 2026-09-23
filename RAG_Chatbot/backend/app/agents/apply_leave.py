"""Bounded deterministic parsing for the single enabled future action."""
from __future__ import annotations
import re
from difflib import get_close_matches
from datetime import date, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
    "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS)
_MONTH_FIRST = re.compile(rf"\b(?P<month>{_MONTH_PATTERN})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s*,\s*(?P<year>\d{{4}})\b", re.IGNORECASE)
_DAY_FIRST = re.compile(rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH_PATTERN})\s+(?P<year>\d{{4}})\b", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_DURATION_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_DURATION_PATTERN = re.compile(
    r"\b(?P<count>\d+|" + "|".join(_DURATION_WORDS) + r")\s+(?:calendar\s+)?days?\b",
    re.IGNORECASE,
)
_INVALID_DURATION_PATTERN = re.compile(r"(?:\b(?:zero|0)\b|-\d+)\s+(?:calendar\s+)?days?\b", re.IGNORECASE)


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


def _explicit_date(message: str) -> tuple[date | None, str | None]:
    match = _MONTH_FIRST.search(message) or _DAY_FIRST.search(message)
    if match:
        try:
            return date(int(match.group("year")), _MONTHS[match.group("month").lower()], int(match.group("day"))), None
        except ValueError:
            return None, "That calendar date is not valid. Please provide a valid date."
    if _NUMERIC_DATE.search(message):
        return None, "Numeric dates can be ambiguous. Please use a month-name date with a four-digit year."
    return None, None


def _relative_date(text: str, today: date) -> date | None:
    if re.search(r"\btoday\b", text):
        return today
    if re.search(r"\btomorrow\b", text):
        return today + timedelta(days=1)
    return None


def _duration_days(text: str) -> tuple[int, str | None]:
    if _INVALID_DURATION_PATTERN.search(text):
        return 0, "Leave duration must be a positive number of days."
    match = _DURATION_PATTERN.search(text)
    if match is None:
        return 1, None
    raw = match.group("count").lower()
    count = _DURATION_WORDS.get(raw, int(raw) if raw.isdigit() else 0)
    if not 1 <= count <= 31:
        return 0, "Please provide a leave duration between 1 and 31 days."
    return count, None


def parse_apply_leave(message: str, today: date | None = None) -> tuple[ApplyLeaveInput | None, str | None]:
    text = " ".join(message.lower().split())
    current_day = today or date.today()
    leave_type = next((kind for kind in ("casual", "medical", "emergency") if f"{kind} leave" in text), None)
    if leave_type is None:
        typed_leave = re.search(r"\b([a-z]+)\s+leave\b", text)
        if typed_leave:
            matches = get_close_matches(typed_leave.group(1), ("casual", "medical", "emergency"), n=1, cutoff=0.82)
            leave_type = matches[0] if matches else None
    if "day off" in text:
        leave_type = "day_off"
    if leave_type is None:
        return None, "Please specify leave type (Casual, Medical, Emergency, or Day Off) and a reason."
    explicit, date_error = _explicit_date(message)
    if date_error:
        return None, date_error
    if explicit is not None:
        resolved = explicit
    elif (relative := _relative_date(text, current_day)) is not None:
        resolved = relative
    else:
        return None, "Please provide an explicit date, today, or tomorrow; ambiguous dates are not guessed."
    days, duration_error = _duration_days(text)
    if duration_error:
        return None, duration_error
    reason = re.search(r"\bbecause\s+(.+?)[.!]?$", message.strip(), re.IGNORECASE)
    reason_text = reason.group(1).strip() if reason and reason.group(1).strip() else f"{leave_type.replace('_', ' ').title()} leave request"
    if leave_type == "day_off":
        if days != 1:
            return None, "Day Off is limited to one half day."
        period = "MORNING" if "morning" in text else "AFTERNOON" if "afternoon" in text else None
        if period is None:
            return None, "Please specify whether the Day Off is for the morning or afternoon."
        return ApplyLeaveInput(leave_type="DAY_OFF", start_date=resolved, end_date=resolved, duration="HALF_DAY", half_day_period=period, reason=reason_text), None
    return ApplyLeaveInput(
        leave_type=leave_type.upper(),
        start_date=resolved,
        end_date=resolved + timedelta(days=days - 1),
        duration="FULL_DAY",
        reason=reason_text,
    ), None
