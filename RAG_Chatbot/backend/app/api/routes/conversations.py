"""Authenticated, owner-scoped Agent conversation APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

from app.api.dependencies import InfoTechIdentity
from app.services.infotech_conversations import (
    AgentConversation,
    ConversationNotFound,
    ConversationStoreError,
)


router = APIRouter(prefix="/api/v1/agent/conversations", tags=["infotech-agent-conversations"])


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=120)


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    created_at: str
    updated_at: str


def _error(exc: ConversationStoreError) -> HTTPException:
    if isinstance(exc, ConversationNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Conversation is unavailable")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Conversation storage is temporarily unavailable")


def _summary(item: AgentConversation) -> ConversationSummary:
    return ConversationSummary(id=item.id, title=item.title, created_at=item.created_at.isoformat(), updated_at=item.updated_at.isoformat())


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
def create_conversation(body: ConversationCreate, request: Request, identity: InfoTechIdentity) -> ConversationSummary:
    try:
        item = request.app.state.infotech_conversations.create(identity.employee_id, body.title.strip() if body.title else "New conversation")
        return _summary(item)
    except ConversationStoreError as exc:
        raise _error(exc) from exc


@router.get("", response_model=list[ConversationSummary])
def list_conversations(request: Request, identity: InfoTechIdentity) -> list[ConversationSummary]:
    try:
        return [_summary(item) for item in request.app.state.infotech_conversations.list(identity.employee_id)]
    except ConversationStoreError as exc:
        raise _error(exc) from exc


@router.get("/{conversation_id}")
def get_conversation(conversation_id: UUID, request: Request, identity: InfoTechIdentity) -> AgentConversation:
    try:
        return request.app.state.infotech_conversations.get(identity.employee_id, conversation_id)
    except ConversationStoreError as exc:
        raise _error(exc) from exc


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: UUID, request: Request, identity: InfoTechIdentity) -> None:
    try:
        request.app.state.infotech_conversations.delete(identity.employee_id, conversation_id)
    except ConversationStoreError as exc:
        raise _error(exc) from exc
