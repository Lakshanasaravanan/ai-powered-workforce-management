"""Redis-coordinated, non-executing pending-action foundation for InfoTech.

Step 3 intentionally does not recover ``EXECUTING`` records.  A process loss
after a future EMS request could otherwise replay an unknown outcome.  Real
execution recovery belongs to the later executor together with EMS-side
idempotency using this record's persisted idempotency key.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class InfoTechActionName(StrEnum):
    APPLY_LEAVE = "apply_leave"
    APPROVE_LEAVE = "approve_leave"
    REJECT_LEAVE = "reject_leave"


class InfoTechActionState(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    VALIDATED_NOT_EXECUTED = "validated_not_executed"


class InfoTechPendingAction(BaseModel):
    """Internal record. Arguments are canonical JSON, never public API fields."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID
    actor_employee_id: UUID
    conversation_id: UUID
    tool_name: InfoTechActionName
    validated_arguments_json: str
    safe_display_json: str
    target_entity_id: UUID | None = None
    created_at: datetime
    expires_at: datetime
    state: InfoTechActionState
    idempotency_key: str = Field(min_length=32)
    execution_started_at: datetime | None = None

    @property
    def validated_arguments(self) -> dict[str, Any]:
        return json.loads(self.validated_arguments_json)

    @property
    def safe_display(self) -> dict[str, Any]:
        return json.loads(self.safe_display_json)


class InfoTechPendingActionPublic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action_id: UUID
    tool_name: InfoTechActionName
    safe_display: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    state: InfoTechActionState


def to_public(action: InfoTechPendingAction) -> InfoTechPendingActionPublic:
    return InfoTechPendingActionPublic(action_id=action.action_id, tool_name=action.tool_name, safe_display=action.safe_display, created_at=action.created_at, expires_at=action.expires_at, state=action.state)


class PendingActionError(RuntimeError):
    pass
class PendingActionUnavailable(PendingActionError):
    pass
class PendingActionExpired(PendingActionError):
    pass
class PendingActionStateError(PendingActionError):
    pass
class PendingActionStoreUnavailable(PendingActionError):
    pass
class PendingActionMalformed(PendingActionError):
    pass


class UnavailableInfoTechPendingActionStore:
    """Fail-closed store used when Redis coordination is not available."""
    def create(self, *args, **kwargs): raise PendingActionStoreUnavailable("Pending actions are temporarily unavailable")
    def claim(self, *args, **kwargs): raise PendingActionStoreUnavailable("Pending actions are temporarily unavailable")
    def cancel(self, *args, **kwargs): raise PendingActionStoreUnavailable("Pending actions are temporarily unavailable")


class RedisInfoTechPendingActionStore:
    """Namespaced Redis CAS store; it holds no bearer token or HTTP metadata."""
    def __init__(self, client, ttl: timedelta = timedelta(minutes=5), execution_lease: timedelta = timedelta(seconds=60)) -> None:
        self._client, self._ttl, self._execution_lease = client, ttl, execution_lease

    @staticmethod
    def _key(action_id: UUID) -> str:
        return f"infotech:agent:pending:{action_id}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _load(self, raw: str | None) -> InfoTechPendingAction:
        if raw is None:
            raise PendingActionUnavailable("Pending action is unavailable")
        try:
            return InfoTechPendingAction.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError) as exc:
            raise PendingActionMalformed("Pending action is unavailable") from exc

    @staticmethod
    def _canonical(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def create(self, *, actor_employee_id: UUID, conversation_id: UUID, tool_name: InfoTechActionName, validated_arguments: dict[str, Any], safe_display: dict[str, Any], target_entity_id: UUID | None = None) -> InfoTechPendingAction:
        now = self._now(); action = InfoTechPendingAction(
            action_id=uuid4(), actor_employee_id=actor_employee_id, conversation_id=conversation_id,
            tool_name=tool_name, validated_arguments_json=self._canonical(validated_arguments),
            safe_display_json=self._canonical(safe_display), target_entity_id=target_entity_id,
            created_at=now, expires_at=now + self._ttl, state=InfoTechActionState.PENDING_CONFIRMATION,
            idempotency_key=secrets.token_urlsafe(32),
        )
        try:
            if not self._client.set(self._key(action.action_id), action.model_dump_json(), ex=max(1, int(self._ttl.total_seconds()) + 1), nx=True):
                raise PendingActionStoreUnavailable("Pending action could not be stored")
        except Exception as exc:
            if redis is not None and isinstance(exc, redis.RedisError):
                raise PendingActionStoreUnavailable("Pending actions are temporarily unavailable") from exc
            raise
        return action

    def _bound(self, action: InfoTechPendingAction, actor_employee_id: UUID, conversation_id: UUID) -> None:
        if action.actor_employee_id != actor_employee_id or action.conversation_id != conversation_id:
            raise PendingActionUnavailable("Pending action is unavailable")

    def _transition(self, action_id: UUID, actor_employee_id: UUID, conversation_id: UUID, allowed: set[InfoTechActionState], next_state: InfoTechActionState, reclaim: bool = False) -> InfoTechPendingAction:
        key = self._key(action_id)
        try:
            with self._client.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(key); action = self._load(pipe.get(key)); self._bound(action, actor_employee_id, conversation_id)
                        if self._now() >= action.expires_at:
                            expired = action.model_copy(update={"state": InfoTechActionState.EXPIRED})
                            pipe.multi(); pipe.set(key, expired.model_dump_json(), keepttl=True); pipe.execute()
                            raise PendingActionExpired("Pending action has expired")
                        if reclaim and action.state is InfoTechActionState.EXECUTING:
                            if action.execution_started_at is None or self._now() - action.execution_started_at < self._execution_lease:
                                raise PendingActionStateError("Pending action is unavailable")
                        if action.state not in allowed:
                            raise PendingActionStateError("Pending action is unavailable")
                        changes: dict[str, Any] = {"state": next_state}
                        if next_state is InfoTechActionState.EXECUTING: changes["execution_started_at"] = self._now()
                        updated = action.model_copy(update=changes)
                        pipe.multi(); pipe.set(key, updated.model_dump_json(), keepttl=True); pipe.execute(); return updated
                    except Exception as exc:
                        if redis is not None and isinstance(exc, redis.WatchError): continue
                        raise
                    finally: pipe.reset()
        except PendingActionError: raise
        except Exception as exc:
            if redis is not None and isinstance(exc, redis.RedisError):
                raise PendingActionStoreUnavailable("Pending actions are temporarily unavailable") from exc
            raise

    def claim(self, action_id: UUID, actor_employee_id: UUID, conversation_id: UUID) -> InfoTechPendingAction:
        # Stale executions can be safely reclaimed only because EMS receives the
        # same persisted idempotency key on every attempt.
        try:
            action = self._load(self._client.get(self._key(action_id)))
            allowed = {InfoTechActionState.PENDING_CONFIRMATION}
            if action.state is InfoTechActionState.EXECUTING and action.execution_started_at and self._now() - action.execution_started_at >= self._execution_lease:
                allowed.add(InfoTechActionState.EXECUTING)
            return self._transition(action_id, actor_employee_id, conversation_id, allowed, InfoTechActionState.EXECUTING, reclaim=True)
        except PendingActionError:
            raise

    def finish_succeeded(self, action_id: UUID, actor_employee_id: UUID, conversation_id: UUID) -> InfoTechPendingAction:
        return self._transition(action_id, actor_employee_id, conversation_id, {InfoTechActionState.EXECUTING}, InfoTechActionState.SUCCEEDED)

    def finish_failed(self, action_id: UUID, actor_employee_id: UUID, conversation_id: UUID) -> InfoTechPendingAction:
        return self._transition(action_id, actor_employee_id, conversation_id, {InfoTechActionState.EXECUTING}, InfoTechActionState.FAILED)

    def cancel(self, action_id: UUID, actor_employee_id: UUID, conversation_id: UUID) -> InfoTechPendingAction:
        return self._transition(action_id, actor_employee_id, conversation_id, {InfoTechActionState.PENDING_CONFIRMATION}, InfoTechActionState.CANCELLED)

    def finish_validated_not_executed(self, action_id: UUID, actor_employee_id: UUID, conversation_id: UUID) -> InfoTechPendingAction:
        return self._transition(action_id, actor_employee_id, conversation_id, {InfoTechActionState.EXECUTING}, InfoTechActionState.VALIDATED_NOT_EXECUTED)


class NonExecutingActionExecutor:
    """Step 3 executor: deliberately never calls EMS or any workforce provider."""
    def execute(self, store: RedisInfoTechPendingActionStore, action: InfoTechPendingAction) -> InfoTechPendingAction:
        return store.finish_validated_not_executed(action.action_id, action.actor_employee_id, action.conversation_id)
