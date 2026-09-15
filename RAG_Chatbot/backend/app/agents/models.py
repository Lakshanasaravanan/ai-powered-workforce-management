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
