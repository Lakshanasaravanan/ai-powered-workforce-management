"""Public request and response contracts for the safe Phase 4 agent layer."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.rag import SourceCitation


class AgentStatus(StrEnum):
    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    SUCCEEDED = "succeeded"
    ERROR = "error"


class ToolCategory(StrEnum):
    KNOWLEDGE = "knowledge"
    SELF_READ = "self_read"
    ACTION_PROPOSE = "action_propose"


class ToolPermission(StrEnum):
    KNOWLEDGE = "knowledge"
    SELF_READ = "self_read"
    ACTION_PROPOSE = "action_propose"


class PendingActionStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class ToolInvocation(BaseModel):
    """An untrusted planner proposal, validated again by ToolRegistry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    category: ToolCategory
    status: str


class PendingAction(BaseModel):
    """Internal in-memory proposal; it contains no execution result."""

    model_config = ConfigDict(frozen=True)

    action_id: UUID
    employee_id: str
    conversation_id: UUID
    tool_name: str
    execution_arguments: dict[str, Any]
    sanitized_arguments: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    status: PendingActionStatus
    confirmation_required: bool = True
    idempotency_key: str
    execution_started_at: datetime | None = None


class PendingActionPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: UUID
    tool_name: str
    sanitized_arguments: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    status: PendingActionStatus
    confirmation_required: bool


class AgentResponse(BaseModel):
    answer: str
    conversation_id: UUID
    sources: list[SourceCitation] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.COMPLETED
    tool: ToolResultSummary | None = None
    pending_action: PendingActionPublic | None = None


class ConfirmationRequest(BaseModel):
    """Only opaque server-issued identifiers may be confirmed by a client."""

    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    conversation_id: UUID
