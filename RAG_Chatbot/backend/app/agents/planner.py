"""Small deterministic planner; it proposes tools but never executes them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.schemas.agent import ToolInvocation
from app.schemas.workforce import AttendancePeriod


DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


@dataclass(frozen=True)
class Plan:
    invocation: ToolInvocation | None = None
    clarification: str | None = None


class DeterministicPlanner:
    """Intent routing deliberately limited to a few transparent Phase 4 rules."""

    def plan(self, message: str) -> Plan:
        normalized = message.strip().lower()
        if "regulariz" in normalized and "attendance" in normalized:
            dates = DATE_PATTERN.findall(normalized)
            if len(dates) != 1:
                return Plan(clarification="Please provide one attendance date in YYYY-MM-DD format before I prepare a proposal.")
            return Plan(invocation=ToolInvocation(tool_name="regularize_attendance", arguments={"attendance_date": dates[0], "requested_status": "present"}))
        if any(term in normalized for term in ("apply leave", "request leave", "take leave")):
            dates = DATE_PATTERN.findall(normalized)
            if "tomorrow" in normalized and not dates:
                tomorrow = (date.today() + timedelta(days=1)).isoformat()
                dates = [tomorrow, tomorrow]
            if len(dates) != 2:
                return Plan(clarification="Please provide leave start and end dates in YYYY-MM-DD format before I prepare a proposal.")
            return Plan(invocation=ToolInvocation(tool_name="request_leave", arguments={"start_date": dates[0], "end_date": dates[1]}))
        if "leave balance" in normalized or "leave remaining" in normalized:
            return Plan(invocation=ToolInvocation(tool_name="get_my_leave_balance"))
        if "attendance" in normalized and any(term in normalized for term in ("summary", "show", "my attendance")):
            period = AttendancePeriod.LAST_30_DAYS if "30" in normalized else AttendancePeriod.SLAMS_AGGREGATE
            return Plan(invocation=ToolInvocation(tool_name="get_my_attendance_summary", arguments={"period": period.value}))
        if "profile" in normalized or "my details" in normalized:
            return Plan(invocation=ToolInvocation(tool_name="get_my_profile"))
        return Plan(invocation=ToolInvocation(tool_name="policy_answer", arguments={"question": message}))
