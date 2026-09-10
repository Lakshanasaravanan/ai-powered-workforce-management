"""Short-lived, in-memory proposal state. Confirmation never executes a mutation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.agents.models import ExecutionContext
from app.schemas.agent import PendingAction, PendingActionPublic, PendingActionStatus


class PendingActionError(RuntimeError):
    code = "pending_action_error"


class PendingActionNotFound(PendingActionError):
    code = "pending_action_not_found"


class PendingActionExpired(PendingActionError):
    code = "pending_action_expired"


class PendingActionAlreadyConfirmed(PendingActionError):
    code = "pending_action_already_confirmed"


def to_public(action: PendingAction) -> PendingActionPublic:
    return PendingActionPublic(
        action_id=action.action_id,
        tool_name=action.tool_name,
        sanitized_arguments=action.sanitized_arguments,
        created_at=action.created_at,
        expires_at=action.expires_at,
        status=action.status,
        confirmation_required=action.confirmation_required,
    )


class PendingActionStore:
    def __init__(self, ttl: timedelta = timedelta(minutes=5)) -> None:
        self.ttl = ttl
        self._actions: dict[UUID, PendingAction] = {}

    def create(self, context: ExecutionContext, tool_name: str, sanitized_arguments: dict[str, object]) -> PendingAction:
        now = datetime.now(timezone.utc)
        action = PendingAction(
            action_id=uuid4(), employee_id=context.employee_id, conversation_id=context.conversation_id,
            tool_name=tool_name, sanitized_arguments=sanitized_arguments, created_at=now,
            expires_at=now + self.ttl, status=PendingActionStatus.PENDING_CONFIRMATION,
        )
        self._actions[action.action_id] = action
        return action

    def confirm(self, action_id: UUID, context: ExecutionContext) -> PendingAction:
        action = self._actions.get(action_id)
        # Deliberately collapse ownership and conversation mismatches into not-found.
        if action is None or action.employee_id != context.employee_id or action.conversation_id != context.conversation_id:
            raise PendingActionNotFound("Pending action is unavailable")
        if action.status is PendingActionStatus.CONFIRMED_NOT_EXECUTED:
            raise PendingActionAlreadyConfirmed("Pending action has already been confirmed")
        if action.status is PendingActionStatus.EXPIRED or datetime.now(timezone.utc) >= action.expires_at:
            expired = action.model_copy(update={"status": PendingActionStatus.EXPIRED})
            self._actions[action_id] = expired
            raise PendingActionExpired("Pending action has expired")
        confirmed = action.model_copy(update={"status": PendingActionStatus.CONFIRMED_NOT_EXECUTED})
        self._actions[action_id] = confirmed
        return confirmed
