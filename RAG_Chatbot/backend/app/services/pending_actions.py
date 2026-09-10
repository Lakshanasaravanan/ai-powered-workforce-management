"""Short-lived, in-memory proposal state. Confirmation never executes a mutation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
import logging
from uuid import UUID, uuid4

from app.agents.models import ExecutionContext
from app.schemas.agent import PendingAction, PendingActionPublic, PendingActionStatus
logger = logging.getLogger("agentic_rag.pending_actions")

try:
    import redis
except ImportError:  # pragma: no cover - dependency is required in production extra
    redis = None


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
        self._lock = Lock()

    def create(self, context: ExecutionContext, tool_name: str, execution_arguments: dict[str, object], sanitized_arguments: dict[str, object]) -> PendingAction:
        now = datetime.now(timezone.utc)
        action_id = uuid4()
        action = PendingAction(
            action_id=action_id, employee_id=context.employee_id, conversation_id=context.conversation_id,
            tool_name=tool_name, execution_arguments=execution_arguments, sanitized_arguments=sanitized_arguments, created_at=now,
            expires_at=now + self.ttl, status=PendingActionStatus.PENDING_CONFIRMATION,
            idempotency_key=f"agent-action-{action_id}",
        )
        with self._lock: self._actions[action.action_id] = action
        logger.info("pending_action_created", extra={"employee_id": context.employee_id, "action_id": str(action.action_id), "tool_name": tool_name, "status": action.status})
        return action

    def confirm(self, action_id: UUID, context: ExecutionContext) -> PendingAction:
        with self._lock:
            action = self._actions.get(action_id)
            if action is None or action.employee_id != context.employee_id or action.conversation_id != context.conversation_id:
                raise PendingActionNotFound("Pending action is unavailable")
            if action.status is not PendingActionStatus.PENDING_CONFIRMATION:
                raise PendingActionAlreadyConfirmed("Pending action has already been confirmed")
            if datetime.now(timezone.utc) >= action.expires_at:
                self._actions[action_id] = action.model_copy(update={"status": PendingActionStatus.EXPIRED})
                raise PendingActionExpired("Pending action has expired")
            confirmed = action.model_copy(update={"status": PendingActionStatus.EXECUTING, "execution_started_at": datetime.now(timezone.utc)})
            self._actions[action_id] = confirmed
            logger.info("pending_action_claimed", extra={"employee_id": context.employee_id, "action_id": str(action_id), "tool_name": action.tool_name, "status": confirmed.status})
            return confirmed

    def finish(self, action_id: UUID, status: PendingActionStatus) -> PendingAction:
        with self._lock:
            action = self._actions[action_id]
            finished = action.model_copy(update={"status": status})
            self._actions[action_id] = finished
            logger.info("pending_action_succeeded" if status is PendingActionStatus.SUCCEEDED else "pending_action_failed", extra={"action_id": str(action_id), "tool_name": action.tool_name, "status": status})
            return finished


class RedisPendingActionStore:
    """Redis-backed action repository with Lua compare-and-set claims across replicas."""
    def __init__(self, client, ttl: timedelta = timedelta(minutes=5), execution_lease: timedelta = timedelta(seconds=60)) -> None:
        self.client, self.ttl, self.execution_lease = client, ttl, execution_lease
    @staticmethod
    def _key(action_id: UUID) -> str: return f"pending-action:{action_id}"
    @staticmethod
    def _dump(action: PendingAction) -> str: return action.model_dump_json()
    @staticmethod
    def _load(raw) -> PendingAction:
        if raw is None: raise PendingActionNotFound("Pending action is unavailable")
        return PendingAction.model_validate_json(raw)
    def create(self, context, tool_name, execution_arguments, sanitized_arguments) -> PendingAction:
        now = datetime.now(timezone.utc); action_id = uuid4()
        action = PendingAction(action_id=action_id, employee_id=context.employee_id, conversation_id=context.conversation_id, tool_name=tool_name, execution_arguments=execution_arguments, sanitized_arguments=sanitized_arguments, created_at=now, expires_at=now+self.ttl, status=PendingActionStatus.PENDING_CONFIRMATION, idempotency_key=f"agent-action-{action_id}")
        self.client.set(self._key(action_id), self._dump(action), ex=int(self.ttl.total_seconds()), nx=True)
        logger.info("pending_action_created", extra={"employee_id": context.employee_id, "action_id": str(action_id), "tool_name": tool_name, "status": action.status})
        return action
    def confirm(self, action_id: UUID, context: ExecutionContext) -> PendingAction:
        key = self._key(action_id)
        with self.client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key); action = self._load(pipe.get(key))
                    if action.employee_id != context.employee_id or action.conversation_id != context.conversation_id: raise PendingActionNotFound("Pending action is unavailable")
                    recover = action.status is PendingActionStatus.EXECUTING and action.execution_started_at and datetime.now(timezone.utc) - action.execution_started_at >= self.execution_lease
                    if action.status is not PendingActionStatus.PENDING_CONFIRMATION and not recover: raise PendingActionAlreadyConfirmed("Pending action is already being processed or completed")
                    if datetime.now(timezone.utc) >= action.expires_at:
                        pipe.multi(); pipe.set(key, self._dump(action.model_copy(update={"status": PendingActionStatus.EXPIRED})), keepttl=True); pipe.execute(); logger.info("pending_action_expired", extra={"action_id": str(action_id), "tool_name": action.tool_name, "status": "expired"}); raise PendingActionExpired("Pending action has expired")
                    claimed = action.model_copy(update={"status": PendingActionStatus.EXECUTING, "execution_started_at": datetime.now(timezone.utc)})
                    pipe.multi(); pipe.set(key, self._dump(claimed), keepttl=True); pipe.execute(); logger.info("pending_action_recovery_claimed" if recover else "pending_action_claimed", extra={"employee_id": context.employee_id, "action_id": str(action_id), "tool_name": action.tool_name, "status": claimed.status}); return claimed
                except Exception as exc:
                    if redis is not None and isinstance(exc, redis.WatchError): continue
                    raise
                finally: pipe.reset()
    def finish(self, action_id: UUID, status: PendingActionStatus) -> PendingAction:
        key=self._key(action_id)
        with self.client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key); action=self._load(pipe.get(key)); updated=action.model_copy(update={"status":status}); pipe.multi(); pipe.set(key,self._dump(updated),keepttl=True); pipe.execute(); return updated
                except Exception as exc:
                    if redis is not None and isinstance(exc, redis.WatchError): continue
                    raise
                finally: pipe.reset()
