"""Proposal-only action tools. They create no workforce side effects."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.models import ExecutionContext
from app.schemas.agent import PendingActionPublic, ToolCategory, ToolPermission
from app.services.pending_actions import PendingActionStore, to_public
from app.tools.base import Tool, ToolSpec


class LeaveRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_range(self) -> "LeaveRequestInput":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class AttendanceRegularizationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attendance_date: date
    requested_status: str = Field(min_length=1, max_length=40)
    reason: str | None = Field(default=None, max_length=500)


class ActionProposalResult(BaseModel):
    pending_action: PendingActionPublic


class _ProposalTool(Tool):
    def __init__(self, store: PendingActionStore) -> None:
        self.store = store

    def _propose(self, context: ExecutionContext, tool_input: BaseModel) -> ActionProposalResult:
        # Free-text reasons are deliberately not retained in Phase 4's temporary proposal store.
        # JSON-mode serialization stores only validated, non-sensitive action details; nothing is executed.
        sanitized = tool_input.model_dump(mode="json", exclude={"reason"})
        action = self.store.create(context, self.spec.name, sanitized)
        return ActionProposalResult(pending_action=to_public(action))


class RequestLeaveTool(_ProposalTool):
    spec = ToolSpec(name="request_leave", description="Create a leave request proposal that requires confirmation.", category=ToolCategory.ACTION_PROPOSE, permission=ToolPermission.ACTION_PROPOSE, requires_confirmation=True)
    input_model = LeaveRequestInput

    def execute(self, context: ExecutionContext, tool_input: LeaveRequestInput) -> ActionProposalResult:
        return self._propose(context, tool_input)


class RegularizeAttendanceTool(_ProposalTool):
    spec = ToolSpec(name="regularize_attendance", description="Create an attendance regularization proposal that requires confirmation.", category=ToolCategory.ACTION_PROPOSE, permission=ToolPermission.ACTION_PROPOSE, requires_confirmation=True)
    input_model = AttendanceRegularizationInput

    def execute(self, context: ExecutionContext, tool_input: AttendanceRegularizationInput) -> ActionProposalResult:
        return self._propose(context, tool_input)
