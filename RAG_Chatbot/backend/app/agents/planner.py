"""Small deterministic planner; it proposes tools but never executes them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.schemas.agent import ToolInvocation
from app.schemas.workforce import AttendancePeriod


DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
ID_PATTERN = re.compile(r"\b(?:id|record)\s*#?\s*(\d+)\b")
TIME_PATTERN = re.compile(r"\b([01]\d|2[0-3]):[0-5]\d\b")


@dataclass(frozen=True)
class Plan:
    invocation: ToolInvocation | None = None
    clarification: str | None = None


class DeterministicPlanner:
    """Intent routing deliberately limited to a few transparent Phase 4 rules."""

    def plan(self, message: str) -> Plan:
        normalized = message.strip().lower()
        if "regulariz" in normalized and "attendance" in normalized:
            record = ID_PATTERN.search(normalized); times = TIME_PATTERN.findall(normalized)
            if record is None or not times or "because" not in normalized: return Plan(clarification="Please provide an attendance record ID, requested check-in time, and reason before I prepare a proposal.")
            args = {"attendance_id": int(record.group(1)), "requested_in_time": times[0] + ":00", "reason": normalized.split("because", 1)[1].strip()}
            if len(times) > 1: args["requested_out_time"] = times[1] + ":00"
            return Plan(invocation=ToolInvocation(tool_name="regularize_attendance", arguments=args))
        if "leave" in normalized and any(term in normalized for term in ("apply", "request", "take")):
            dates = DATE_PATTERN.findall(normalized)
            leave_type = next((kind for kind in ("casual", "sick", "earned") if kind in normalized), None)
            if len(dates) != 2 or leave_type is None or "because" not in normalized: return Plan(clarification="Please provide leave type (CASUAL, SICK, or EARNED), start and end dates, and a reason.")
            return Plan(invocation=ToolInvocation(tool_name="request_leave", arguments={"leave_type": leave_type.upper(), "start_date": dates[0], "end_date": dates[1], "reason": normalized.split("because", 1)[1].strip()}))
        if "leave balance" in normalized or "leave remaining" in normalized:
            return Plan(invocation=ToolInvocation(tool_name="get_my_leave_balance"))
        if "attendance" in normalized and any(term in normalized for term in ("records", "recent", "which attendance record")):
            return Plan(invocation=ToolInvocation(tool_name="get_my_attendance_records"))
        if "attendance" in normalized and any(term in normalized for term in ("summary", "show", "my attendance")):
            period = AttendancePeriod.LAST_30_DAYS if "30" in normalized else AttendancePeriod.SLAMS_AGGREGATE
            return Plan(invocation=ToolInvocation(tool_name="get_my_attendance_summary", arguments={"period": period.value}))
        if "profile" in normalized or "my details" in normalized:
            return Plan(invocation=ToolInvocation(tool_name="get_my_profile"))
        return Plan(invocation=ToolInvocation(tool_name="policy_answer", arguments={"question": message}))
