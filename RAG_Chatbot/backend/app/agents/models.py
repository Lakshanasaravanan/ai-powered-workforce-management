"""Server-owned execution models not supplied by a planner or client."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    employee_id: str
    display_name: str
    roles: frozenset[str]
    request_id: str
    conversation_id: UUID
    auth_subject: str


@dataclass(frozen=True, slots=True)
class PolicyExecutionContext:
    """Minimum EMS-derived identity required by the InfoTech policy-QA path."""

    employee_id: UUID
    employee_code: str
    display_name: str
    role: str
    request_id: str | None
    conversation_id: UUID


@dataclass(frozen=True, slots=True)
class InfoTechAgentExecutionContext:
    """Identity-only context for the new InfoTech EMS tool boundary.

    Transport credentials are deliberately not stored here.  Callers retain the
    current bearer token only for the duration of an EMS client call.
    """

    employee_id: UUID
    employee_code: str
    display_name: str
    role: str
    request_id: str | None
    conversation_id: UUID


def infotech_agent_context(identity, request_id: str | None, conversation_id: UUID) -> InfoTechAgentExecutionContext:
    """Create a tool context only from the verified EMS identity boundary."""

    return InfoTechAgentExecutionContext(
        employee_id=identity.employee_id,
        employee_code=identity.employee_code,
        display_name=identity.display_name,
        role=identity.role,
        request_id=request_id,
        conversation_id=conversation_id,
    )
