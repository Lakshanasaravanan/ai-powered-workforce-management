"""Schema-validated local-LLM routing for requests outside deterministic patterns.

The classifier is advisory only: it can select a small, fixed category and a
fixed EMS read operation. It never provides IDs, arguments, URLs, or authority
to mutate. Consequential requests still pass the deterministic action parser
and confirmation lifecycle.
"""

from __future__ import annotations

import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.services.llm import LLMProvider, LLMProviderError


class SemanticCategory(StrEnum):
    GENERAL = "general"
    POLICY = "policy"
    EMS_READ = "ems_read"
    EMS_ACTION_LEAVE = "ems_action_leave"
    UNSUPPORTED = "unsupported"


class EMSReadOperation(StrEnum):
    MANAGER = "manager"
    PROFILE = "profile"
    LEAVES = "leaves"
    NOTIFICATIONS = "notifications"
    UNREAD_COUNT = "unread_count"
    DIRECT_REPORTS = "direct_reports"
    TEAM_LEAVES = "team_leaves"


READ_TOOL_BY_OPERATION = {
    EMSReadOperation.MANAGER: "get_my_manager",
    EMSReadOperation.PROFILE: "get_my_profile",
    EMSReadOperation.LEAVES: "get_my_leaves",
    EMSReadOperation.NOTIFICATIONS: "get_my_notifications",
    EMSReadOperation.UNREAD_COUNT: "get_unread_notification_count",
    EMSReadOperation.DIRECT_REPORTS: "get_direct_reports",
    EMSReadOperation.TEAM_LEAVES: "get_team_leaves",
}


class SemanticRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: SemanticCategory
    read_operation: EMSReadOperation | None = None
    general_response: str | None = Field(default=None, max_length=2400)

    @model_validator(mode="after")
    def validate_shape(self) -> "SemanticRoute":
        if self.category is SemanticCategory.GENERAL:
            if not self.general_response or not self.general_response.strip():
                raise ValueError("general responses require text")
            if self.read_operation is not None:
                raise ValueError("general responses cannot choose EMS operations")
        elif self.category is SemanticCategory.EMS_READ:
            if self.read_operation is None:
                raise ValueError("EMS reads require an allowlisted operation")
        elif self.read_operation is not None:
            raise ValueError("only EMS reads may select an operation")
        return self


SYSTEM_PROMPT = """You are the semantic routing layer for InfoTech Agent.
Return JSON that matches the supplied schema and nothing else.

Choose general only for ordinary benign, non-company questions. For general,
provide a concise helpful answer while identifying yourself as InfoTech Agent
when relevant. General answers must not claim current employee facts, company
policy, or that an action was performed.

Choose policy for company rules, workplace policies, company practices, or
questions that need company documents. Choose ems_read only for the current
authenticated user's information and select exactly one listed read operation.
Choose ems_action_leave for a request to create the user's own leave request;
never extract action arguments. Choose unsupported for unavailable company
facts, requests about other employees, unsafe requests, or requests that do
not fit safely.

Casual language must not hide a substantive enterprise intent. You cannot
authorize mutations, choose arbitrary tools, supply employee identifiers,
URLs, API calls, SQL, dates, or action arguments."""


class SemanticIntentRouter:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def classify(self, message: str) -> SemanticRoute | None:
        try:
            raw = self._provider.generate(
                SYSTEM_PROMPT,
                f"User message:\n{message}\n\nClassify this request safely.",
                SemanticRoute.model_json_schema(),
            )
            return SemanticRoute.model_validate(json.loads(raw))
        except (LLMProviderError, ValueError, TypeError, ValidationError):
            return None
