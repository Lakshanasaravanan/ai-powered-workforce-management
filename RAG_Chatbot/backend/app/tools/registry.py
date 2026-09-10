"""The sole controlled boundary from a planner proposal to tool execution."""

from __future__ import annotations

import logging
from time import perf_counter

from pydantic import BaseModel, ValidationError

from app.agents.models import ExecutionContext
from app.schemas.agent import ToolInvocation, ToolPermission
from app.tools.base import Tool


audit_logger = logging.getLogger("agentic_rag.tool_audit")


class ToolExecutionError(RuntimeError):
    code = "tool_execution_error"


class UnknownToolError(ToolExecutionError):
    code = "unknown_tool"


class InvalidToolInputError(ToolExecutionError):
    code = "invalid_tool_input"


class UnauthorizedToolError(ToolExecutionError):
    code = "unauthorized_tool"


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.spec.name in self._tools:
                raise ValueError(f"Duplicate tool registration: {tool.spec.name}")
            self._tools[tool.spec.name] = tool

    def names(self) -> set[str]:
        return set(self._tools)

    def spec_for(self, name: str):
        """Return server-defined metadata for a registered tool."""
        return self._resolve(name).spec

    def _resolve(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError("Requested tool is not available")
        return tool

    @staticmethod
    def _authorized(context: ExecutionContext, permission: ToolPermission) -> bool:
        # Phase 4 intentionally has one self-service employee role, not manager/admin access.
        return "employee" in context.roles and permission in {
            ToolPermission.KNOWLEDGE, ToolPermission.SELF_READ, ToolPermission.ACTION_PROPOSE,
        }

    def execute(self, invocation: ToolInvocation, context: ExecutionContext) -> tuple[Tool, BaseModel]:
        started = perf_counter()
        tool_name = invocation.tool_name
        category = "unknown"
        outcome = "error"
        error_code: str | None = None
        pending_action_id: str | None = None
        try:
            tool = self._resolve(tool_name)
            category = tool.spec.category.value
            if not self._authorized(context, tool.spec.permission):
                raise UnauthorizedToolError("You are not permitted to use this tool")
            try:
                validated = tool.input_model.model_validate(invocation.arguments)
            except ValidationError as exc:
                raise InvalidToolInputError("Tool input is invalid") from exc
            result = tool.execute(context, validated)
            pending_action = getattr(result, "pending_action", None)
            if pending_action is not None:
                pending_action_id = str(pending_action.action_id)
            outcome = "success"
            return tool, result
        except ToolExecutionError as exc:
            error_code = exc.code
            raise
        except Exception as exc:
            error_code = getattr(exc, "code", "tool_failed")
            raise
        finally:
            audit_logger.info(
                "tool_audit",
                extra={
                    "request_id": context.request_id,
                    "conversation_id": str(context.conversation_id),
                    "employee_id": context.employee_id,
                    "tool_name": tool_name,
                    "tool_category": category,
                    "result_status": outcome,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "error_code": error_code,
                    "pending_action_id": pending_action_id,
                },
            )
