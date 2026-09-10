"""Deterministic agent orchestration with no direct workforce or RAG implementation."""

from __future__ import annotations

import logging

from app.agents.models import ExecutionContext
from app.agents.planner import DeterministicPlanner
from app.rag.service import RAGServiceError
from app.schemas.agent import AgentResponse, AgentStatus, ConfirmationRequest, ToolResultSummary
from app.schemas.workforce import AttendanceSummary, EmployeeProfile, LeaveBalance
from app.services.pending_actions import (
    PendingActionAlreadyConfirmed,
    PendingActionError,
    PendingActionExpired,
    PendingActionStore,
    PendingActionNotFound,
    to_public,
)
from app.services.workforce import WorkforceProviderError
from app.tools.actions import ActionProposalResult
from app.tools.rag_tool import PolicyAnswerResult
from app.tools.registry import ToolExecutionError, ToolRegistry


logger = logging.getLogger("agentic_rag.agent")


class AgentService:
    def __init__(self, planner: DeterministicPlanner, registry: ToolRegistry, pending_actions: PendingActionStore) -> None:
        self.planner = planner
        self.registry = registry
        self.pending_actions = pending_actions

    @staticmethod
    def _summary(tool, status: str) -> ToolResultSummary:
        return ToolResultSummary(tool_name=tool.spec.name, category=tool.spec.category, status=status)

    @staticmethod
    def _read_answer(result) -> str:
        if isinstance(result, EmployeeProfile):
            department = result.department or "an unspecified department"
            return f"Your profile is {result.display_name} in {department}."
        if isinstance(result, LeaveBalance):
            return f"Your leave balance is {result.annual_days_remaining:g} annual and {result.sick_days_remaining:g} sick days remaining."
        if isinstance(result, AttendanceSummary):
            return f"Your attendance summary for {result.period.value}: {result.present_days} present, {result.leave_days} leave, out of {result.scheduled_days} scheduled days."
        return "Your requested information is available."

    def respond(self, message: str, context: ExecutionContext) -> AgentResponse:
        plan = self.planner.plan(message)
        if plan.clarification:
            return AgentResponse(answer=plan.clarification, conversation_id=context.conversation_id, status=AgentStatus.CLARIFICATION_REQUIRED)
        assert plan.invocation is not None
        try:
            tool, result = self.registry.execute(plan.invocation, context)
            if isinstance(result, PolicyAnswerResult):
                return AgentResponse(answer=result.answer, conversation_id=context.conversation_id, sources=result.sources, tool=self._summary(tool, "success"))
            if isinstance(result, ActionProposalResult):
                return AgentResponse(
                    answer="Your action proposal is ready for confirmation. No workforce change has been made.",
                    conversation_id=context.conversation_id,
                    status=AgentStatus.CONFIRMATION_REQUIRED,
                    tool=self._summary(tool, "proposal_created"),
                    pending_action=result.pending_action,
                )
            return AgentResponse(answer=self._read_answer(result), conversation_id=context.conversation_id, tool=self._summary(tool, "success"))
        except RAGServiceError:
            raise
        except (ToolExecutionError, WorkforceProviderError) as exc:
            logger.warning("agent_tool_failed", extra={"request_id": context.request_id, "tool_error_code": getattr(exc, "code", "workforce_unavailable")})
            return AgentResponse(answer="I could not complete that request safely.", conversation_id=context.conversation_id, status=AgentStatus.ERROR)

    def confirm(self, request: ConfirmationRequest, context: ExecutionContext) -> AgentResponse:
        # Request context must bind to the exact conversation supplied to confirmation.
        if request.conversation_id != context.conversation_id:
            return AgentResponse(answer="That pending action is unavailable.", conversation_id=context.conversation_id, status=AgentStatus.ERROR)
        try:
            action = self.pending_actions.confirm(request.action_id, context)
        except (PendingActionNotFound, PendingActionExpired, PendingActionAlreadyConfirmed) as exc:
            logger.warning("pending_action_confirmation_failed", extra={"request_id": context.request_id, "error_code": exc.code})
            return AgentResponse(answer="That pending action is unavailable or can no longer be confirmed.", conversation_id=context.conversation_id, status=AgentStatus.ERROR)
        logger.info(
            "pending_action_confirmed_not_executed",
            extra={
                "request_id": context.request_id,
                "conversation_id": str(context.conversation_id),
                "employee_id": context.employee_id,
                "tool_name": action.tool_name,
                "pending_action_id": str(action.action_id),
                "result_status": "confirmed_not_executed",
            },
        )
        return AgentResponse(
            answer="Action confirmed, but workforce action execution is not enabled in this phase. No leave or attendance record was changed.",
            conversation_id=context.conversation_id,
            status=AgentStatus.CONFIRMED_NOT_EXECUTED,
            tool=ToolResultSummary(tool_name=action.tool_name, category=self.registry.spec_for(action.tool_name).category, status="confirmed_not_executed"),
            pending_action=to_public(action),
        )
