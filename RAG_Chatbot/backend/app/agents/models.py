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
