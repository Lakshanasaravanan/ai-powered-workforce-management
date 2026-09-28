"""Server-side, owner-scoped conversation state for the InfoTech Agent.

This store deliberately contains only user-visible messages and the minimum
structured state needed to continue a pending conversation.  Transport
credentials, provider data, and EMS records never belong here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    role: ConversationRole
    content: str = Field(min_length=1, max_length=6000)
    created_at: datetime
    sources: list[dict[str, Any]] = Field(default_factory=list)
    action: dict[str, Any] | None = None
    result: str | None = None


class ConversationPendingState(BaseModel):
    """Collecting state only; immutable executable actions remain elsewhere."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: str = "apply_leave"
    slots: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class AgentConversation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    owner_employee_id: UUID
    title: str = Field(min_length=1, max_length=120)
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessage] = Field(default_factory=list)
    pending: ConversationPendingState | None = None


class ConversationStoreError(RuntimeError):
    pass


class ConversationNotFound(ConversationStoreError):
    pass


class ConversationStoreUnavailable(ConversationStoreError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def title_for(message: str) -> str:
    lower = message.lower()
    if "leave" in lower or "day off" in lower:
        return "Leave request"
    if "attendance" in lower or "late" in lower or "overtime" in lower:
        return "Attendance question"
    if "payroll" in lower or "salary" in lower:
        return "Payroll question"
    if "manager" in lower:
        return "Manager question"
    if "policy" in lower:
        return "Company policy"
    normalized = " ".join(message.split())
    return normalized[:80] if normalized else "New conversation"


class RedisAgentConversationStore:
    """Redis-backed durable orchestration state, scoped by authenticated owner."""

    def __init__(self, client, pending_ttl: timedelta = timedelta(minutes=10)) -> None:
        self._client = client
        self._pending_ttl = pending_ttl

    @staticmethod
    def _key(conversation_id: UUID, owner_employee_id: UUID) -> str:
        # Owner namespace prevents a legacy client-supplied UUID from ever
        # becoming a cross-user discovery handle.
        return f"infotech:agent:conversation:{owner_employee_id}:{conversation_id}"

    @staticmethod
    def _owner_key(owner_employee_id: UUID) -> str:
        return f"infotech:agent:conversations:{owner_employee_id}"

    def _load(self, conversation_id: UUID, owner_employee_id: UUID) -> AgentConversation:
        try:
            raw = self._client.get(self._key(conversation_id, owner_employee_id))
            if raw is None:
                raise ConversationNotFound("Conversation is unavailable")
            conversation = AgentConversation.model_validate_json(raw)
            # Treat cross-owner access as not found: do not disclose existence.
            if conversation.owner_employee_id != owner_employee_id:
                raise ConversationNotFound("Conversation is unavailable")
            return self._expire_pending(conversation)
        except ConversationStoreError:
            raise
        except Exception as exc:
            raise ConversationStoreUnavailable("Conversation storage is unavailable") from exc

    def _save(self, conversation: AgentConversation) -> AgentConversation:
        try:
            self._client.set(self._key(conversation.id, conversation.owner_employee_id), conversation.model_dump_json())
            self._client.zadd(self._owner_key(conversation.owner_employee_id), {str(conversation.id): conversation.updated_at.timestamp()})
            return conversation
        except Exception as exc:
            raise ConversationStoreUnavailable("Conversation storage is unavailable") from exc

    def _expire_pending(self, conversation: AgentConversation) -> AgentConversation:
        if conversation.pending and conversation.pending.expires_at <= _now():
            return self._save(conversation.model_copy(update={"pending": None, "updated_at": _now()}))
        return conversation

    def create(self, owner_employee_id: UUID, title: str = "New conversation", conversation_id: UUID | None = None) -> AgentConversation:
        now = _now()
        return self._save(AgentConversation(id=conversation_id or uuid4(), owner_employee_id=owner_employee_id, title=title, created_at=now, updated_at=now))

    def get_or_create(self, owner_employee_id: UUID, conversation_id: UUID | None) -> AgentConversation:
        if conversation_id is None:
            return self.create(owner_employee_id)
        try:
            return self._load(conversation_id, owner_employee_id)
        except ConversationNotFound:
            # Query clients from earlier releases supplied their own fresh UUID.
            # Preserve that compatibility without ever opening an existing foreign record.
            try:
                if self._client.get(self._key(conversation_id, owner_employee_id)) is not None:
                    raise
            except ConversationNotFound:
                raise
            return self.create(owner_employee_id, conversation_id=conversation_id)

    def get(self, owner_employee_id: UUID, conversation_id: UUID) -> AgentConversation:
        return self._load(conversation_id, owner_employee_id)

    def list(self, owner_employee_id: UUID) -> list[AgentConversation]:
        try:
            ids = self._client.zrevrange(self._owner_key(owner_employee_id), 0, -1)
        except Exception as exc:
            raise ConversationStoreUnavailable("Conversation storage is unavailable") from exc
        conversations: list[AgentConversation] = []
        for value in ids:
            try:
                conversations.append(self._load(UUID(str(value)), owner_employee_id))
            except ConversationNotFound:
                continue
        return conversations

    def delete(self, owner_employee_id: UUID, conversation_id: UUID) -> None:
        self._load(conversation_id, owner_employee_id)
        try:
            self._client.delete(self._key(conversation_id, owner_employee_id))
            self._client.zrem(self._owner_key(owner_employee_id), str(conversation_id))
        except Exception as exc:
            raise ConversationStoreUnavailable("Conversation storage is unavailable") from exc

    def append(self, owner_employee_id: UUID, conversation_id: UUID, *, role: ConversationRole, content: str, sources: list[dict[str, Any]] | None = None, action: dict[str, Any] | None = None, result: str | None = None) -> AgentConversation:
        conversation = self._load(conversation_id, owner_employee_id)
        now = _now()
        message = ConversationMessage(id=uuid4(), role=role, content=content, created_at=now, sources=sources or [], action=action, result=result)
        title = conversation.title if conversation.messages else title_for(content)
        return self._save(conversation.model_copy(update={"title": title, "updated_at": now, "messages": [*conversation.messages, message]}))

    def set_pending(self, owner_employee_id: UUID, conversation_id: UUID, slots: dict[str, str]) -> AgentConversation:
        conversation = self._load(conversation_id, owner_employee_id)
        now = _now()
        pending = ConversationPendingState(slots=slots, created_at=conversation.pending.created_at if conversation.pending else now, updated_at=now, expires_at=now + self._pending_ttl)
        return self._save(conversation.model_copy(update={"pending": pending, "updated_at": now}))

    def clear_pending(self, owner_employee_id: UUID, conversation_id: UUID) -> AgentConversation:
        conversation = self._load(conversation_id, owner_employee_id)
        return self._save(conversation.model_copy(update={"pending": None, "updated_at": _now()}))


class UnavailableAgentConversationStore:
    def _fail(self, *args, **kwargs):
        raise ConversationStoreUnavailable("Conversation storage is unavailable")
    create = get_or_create = get = list = delete = append = set_pending = clear_pending = _fail
