"""Server-issued opaque references for manager leave-decision proposals."""

from __future__ import annotations

import secrets
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class DecisionReferenceError(RuntimeError):
    pass


class DecisionReferenceUnavailable(DecisionReferenceError):
    pass


class DecisionReferenceExpired(DecisionReferenceError):
    pass


class DecisionReferenceNotFound(DecisionReferenceError):
    pass


class DecisionReferenceBindingError(DecisionReferenceError):
    pass


class LeaveDecisionReference(BaseModel):
    """Internal mapping; the public reference is not an authorization grant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str = Field(pattern=r"^LR-[A-F0-9]{20}$")
    manager_employee_id: UUID
    conversation_id: UUID
    leave_id: UUID
    created_at: datetime
    expires_at: datetime


class UnavailableInfoTechDecisionReferenceStore:
    def issue(self, *args, **kwargs):
        raise DecisionReferenceUnavailable("Leave decision references are temporarily unavailable")

    def resolve(self, *args, **kwargs):
        raise DecisionReferenceUnavailable("Leave decision references are temporarily unavailable")


class RedisInfoTechDecisionReferenceStore:
    """Short-lived opaque mappings in a namespace separate from pending actions."""

    def __init__(self, client, ttl: timedelta = timedelta(minutes=5)) -> None:
        self._client = client
        self._ttl = ttl

    @staticmethod
    def _key(reference: str) -> str:
        return f"infotech:agent:leave-decision-reference:{reference}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _new_reference() -> str:
        # 80 bits of random entropy; it contains no leave or identity material.
        return f"LR-{secrets.token_hex(10).upper()}"

    @staticmethod
    def _load(raw: str | None) -> LeaveDecisionReference:
        if raw is None:
            raise DecisionReferenceNotFound("Leave decision reference is unavailable")
        try:
            return LeaveDecisionReference.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError) as exc:
            raise DecisionReferenceNotFound("Leave decision reference is unavailable") from exc

    def issue(self, *, manager_employee_id: UUID, conversation_id: UUID, leave_id: UUID) -> LeaveDecisionReference:
        now = self._now()
        for _ in range(3):
            reference = self._new_reference()
            record = LeaveDecisionReference(
                reference=reference,
                manager_employee_id=manager_employee_id,
                conversation_id=conversation_id,
                leave_id=leave_id,
                created_at=now,
                expires_at=now + self._ttl,
            )
            try:
                if self._client.set(self._key(reference), record.model_dump_json(), ex=max(1, int(self._ttl.total_seconds())), nx=True):
                    return record
            except Exception as exc:
                if redis is not None and isinstance(exc, redis.RedisError):
                    raise DecisionReferenceUnavailable("Leave decision references are temporarily unavailable") from exc
                raise
        raise DecisionReferenceUnavailable("Leave decision references are temporarily unavailable")

    def resolve(self, reference: str, *, manager_employee_id: UUID, conversation_id: UUID) -> LeaveDecisionReference:
        if not isinstance(reference, str) or not re.fullmatch(r"LR-[A-F0-9]{20}", reference):
            raise DecisionReferenceNotFound("Leave decision reference is unavailable")
        try:
            record = self._load(self._client.get(self._key(reference)))
        except Exception as exc:
            if isinstance(exc, DecisionReferenceError):
                raise
            if redis is not None and isinstance(exc, redis.RedisError):
                raise DecisionReferenceUnavailable("Leave decision references are temporarily unavailable") from exc
            raise
        if self._now() >= record.expires_at:
            raise DecisionReferenceExpired("Leave decision reference has expired")
        if record.manager_employee_id != manager_employee_id or record.conversation_id != conversation_id:
            raise DecisionReferenceBindingError("Leave decision reference is unavailable")
        return record
