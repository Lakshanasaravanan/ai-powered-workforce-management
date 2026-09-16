"""Read-only self-service tools backed only by the synthetic provider."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.agents.models import ExecutionContext
from app.schemas.agent import ToolCategory, ToolPermission
from app.schemas.workforce import AttendancePeriod, AttendanceRecord, AttendanceSummary, EmployeeProfile, LeaveBalance
from app.services.workforce import WorkforceProvider
from app.tools.base import Tool, ToolSpec


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttendanceSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: AttendancePeriod = AttendancePeriod.SLAMS_AGGREGATE


class GetMyProfileTool(Tool):
    spec = ToolSpec(name="get_my_profile", description="Read the authenticated employee's profile.", category=ToolCategory.SELF_READ, permission=ToolPermission.SELF_READ)
    input_model = EmptyInput

    def __init__(self, provider: WorkforceProvider) -> None:
        self.provider = provider

    def execute(self, context: ExecutionContext, tool_input: EmptyInput) -> EmployeeProfile:
        return self.provider.get_profile(context.employee_id, context.request_id)


class GetMyLeaveBalanceTool(Tool):
    spec = ToolSpec(name="get_my_leave_balance", description="Read the authenticated employee's leave balance.", category=ToolCategory.SELF_READ, permission=ToolPermission.SELF_READ)
    input_model = EmptyInput

    def __init__(self, provider: WorkforceProvider) -> None:
        self.provider = provider

    def execute(self, context: ExecutionContext, tool_input: EmptyInput) -> LeaveBalance:
        return self.provider.get_leave_balance(context.employee_id, context.request_id)


class GetMyAttendanceSummaryTool(Tool):
    spec = ToolSpec(name="get_my_attendance_summary", description="Read the authenticated employee's attendance summary.", category=ToolCategory.SELF_READ, permission=ToolPermission.SELF_READ)
    input_model = AttendanceSummaryInput

    def __init__(self, provider: WorkforceProvider) -> None:
        self.provider = provider

    def execute(self, context: ExecutionContext, tool_input: AttendanceSummaryInput) -> AttendanceSummary:
        return self.provider.get_attendance_summary(context.employee_id, tool_input.period, context.request_id)

class GetMyAttendanceRecordsTool(Tool):
    spec = ToolSpec(name="get_my_attendance_records", description="Read the authenticated employee's attendance records.", category=ToolCategory.SELF_READ, permission=ToolPermission.SELF_READ)
    input_model = EmptyInput
    def __init__(self, provider: WorkforceProvider) -> None: self.provider = provider
    def execute(self, context: ExecutionContext, tool_input: EmptyInput) -> list[AttendanceRecord]: return self.provider.get_attendance_records(context.employee_id, context.request_id)
