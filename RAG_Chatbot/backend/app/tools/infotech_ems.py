"""Typed, read-only InfoTech EMS tools for deterministic future routing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.models import InfoTechAgentExecutionContext
from app.services.infotech_ems import (
    EMSLeave,
    EMSManagerResult,
    EMSNotification,
    EMSProfile,
    EMSUnreadCount,
    InfoTechEMSReadClient,
)


class EmptyReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InfoTechReadToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=80)
    description: str
    classification: Literal["read"] = "read"
    allowed_roles: frozenset[Literal["ADMIN", "MANAGER", "EMPLOYEE"]]


class InfoTechToolError(RuntimeError):
    pass


class InfoTechUnknownTool(InfoTechToolError):
    pass


class InfoTechUnauthorizedTool(InfoTechToolError):
    pass


class InfoTechInvalidToolInput(InfoTechToolError):
    pass


class InfoTechReadTool(ABC):
    spec: ClassVar[InfoTechReadToolSpec]
    input_model: ClassVar[type[BaseModel]] = EmptyReadInput

    @abstractmethod
    def execute(
        self,
        context: InfoTechAgentExecutionContext,
        bearer_token: str,
        tool_input: EmptyReadInput,
    ) -> BaseModel | list[BaseModel]: ...


class GetMyProfileTool(InfoTechReadTool):
    spec = InfoTechReadToolSpec(name="get_my_profile", description="Read the authenticated employee profile.", allowed_roles=frozenset({"ADMIN", "MANAGER", "EMPLOYEE"}))

    def __init__(self, client: InfoTechEMSReadClient) -> None:
        self._client = client

    def execute(self, context: InfoTechAgentExecutionContext, bearer_token: str, tool_input: EmptyReadInput) -> EMSProfile:
        return self._client.get_my_profile(bearer_token)


class GetMyManagerTool(InfoTechReadTool):
    spec = InfoTechReadToolSpec(name="get_my_manager", description="Read the authenticated employee's assigned manager.", allowed_roles=frozenset({"ADMIN", "MANAGER", "EMPLOYEE"}))

    def __init__(self, client: InfoTechEMSReadClient) -> None:
        self._client = client

    def execute(self, context: InfoTechAgentExecutionContext, bearer_token: str, tool_input: EmptyReadInput) -> EMSManagerResult:
        return self._client.get_my_manager(bearer_token)


class GetMyLeavesTool(InfoTechReadTool):
    spec = InfoTechReadToolSpec(name="get_my_leaves", description="Read the authenticated employee leave requests.", allowed_roles=frozenset({"ADMIN", "MANAGER", "EMPLOYEE"}))

    def __init__(self, client: InfoTechEMSReadClient) -> None:
        self._client = client

    def execute(self, context: InfoTechAgentExecutionContext, bearer_token: str, tool_input: EmptyReadInput) -> list[EMSLeave]:
        return self._client.get_my_leaves(bearer_token)


class GetMyNotificationsTool(InfoTechReadTool):
    spec = InfoTechReadToolSpec(name="get_my_notifications", description="Read the authenticated employee notifications.", allowed_roles=frozenset({"ADMIN", "MANAGER", "EMPLOYEE"}))

    def __init__(self, client: InfoTechEMSReadClient) -> None:
        self._client = client

    def execute(self, context: InfoTechAgentExecutionContext, bearer_token: str, tool_input: EmptyReadInput) -> list[EMSNotification]:
        return self._client.get_my_notifications(bearer_token)


class GetUnreadNotificationCountTool(InfoTechReadTool):
    spec = InfoTechReadToolSpec(name="get_unread_notification_count", description="Read the authenticated employee unread notification count.", allowed_roles=frozenset({"ADMIN", "MANAGER", "EMPLOYEE"}))

    def __init__(self, client: InfoTechEMSReadClient) -> None:
        self._client = client

    def execute(self, context: InfoTechAgentExecutionContext, bearer_token: str, tool_input: EmptyReadInput) -> EMSUnreadCount:
        return self._client.get_unread_notification_count(bearer_token)


class GetDirectReportsTool(InfoTechReadTool):
    spec = InfoTechReadToolSpec(name="get_direct_reports", description="Read the authenticated Manager's direct reports.", allowed_roles=frozenset({"MANAGER"}))

    def __init__(self, client: InfoTechEMSReadClient) -> None:
        self._client = client

    def execute(self, context: InfoTechAgentExecutionContext, bearer_token: str, tool_input: EmptyReadInput) -> list[EMSProfile]:
        return self._client.get_direct_reports(bearer_token)


class GetTeamLeavesTool(InfoTechReadTool):
    spec = InfoTechReadToolSpec(name="get_team_leaves", description="Read the authenticated Manager's direct-report leave requests.", allowed_roles=frozenset({"MANAGER"}))

    def __init__(self, client: InfoTechEMSReadClient) -> None:
        self._client = client

    def execute(self, context: InfoTechAgentExecutionContext, bearer_token: str, tool_input: EmptyReadInput) -> list[EMSLeave]:
        return self._client.get_team_leaves(bearer_token)


class InfoTechReadToolRegistry:
    """Closed registry for the six safe Phase 5 Step 1 tools."""

    def __init__(self, tools: list[InfoTechReadTool]) -> None:
        self._tools: dict[str, InfoTechReadTool] = {}
        for tool in tools:
            if tool.spec.name in self._tools:
                raise ValueError("Duplicate InfoTech tool registration")
            self._tools[tool.spec.name] = tool

    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def names_for(self, context: InfoTechAgentExecutionContext) -> frozenset[str]:
        return frozenset(name for name, tool in self._tools.items() if context.role in tool.spec.allowed_roles)

    def execute(
        self,
        tool_name: str,
        context: InfoTechAgentExecutionContext,
        bearer_token: str,
        arguments: object | None = None,
    ) -> BaseModel | list[BaseModel]:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise InfoTechUnknownTool("Requested InfoTech tool is unavailable")
        if context.role not in tool.spec.allowed_roles:
            raise InfoTechUnauthorizedTool("InfoTech tool is unavailable for this role")
        try:
            tool_input = tool.input_model.model_validate({} if arguments is None else arguments)
        except ValidationError as exc:
            raise InfoTechInvalidToolInput("InfoTech tool input is invalid") from exc
        return tool.execute(context, bearer_token, tool_input)


def build_infotech_read_registry(client: InfoTechEMSReadClient) -> InfoTechReadToolRegistry:
    return InfoTechReadToolRegistry([
        GetMyProfileTool(client),
        GetMyManagerTool(client),
        GetMyLeavesTool(client),
        GetMyNotificationsTool(client),
        GetUnreadNotificationCountTool(client),
        GetDirectReportsTool(client),
        GetTeamLeavesTool(client),
    ])
