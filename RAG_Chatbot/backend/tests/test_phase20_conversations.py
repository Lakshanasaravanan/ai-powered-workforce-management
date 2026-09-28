from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import fakeredis
import pytest

from app.services.infotech_conversations import (
    ConversationNotFound,
    ConversationRole,
    RedisAgentConversationStore,
)


OWNER_A = UUID("11111111-1111-4111-8111-111111111111")
OWNER_B = UUID("22222222-2222-4222-8222-222222222222")


def store() -> RedisAgentConversationStore:
    return RedisAgentConversationStore(fakeredis.FakeRedis(decode_responses=True), pending_ttl=timedelta(minutes=5))


def test_conversation_messages_are_persistent_and_owner_scoped():
    service = store()
    conversation = service.create(OWNER_A)
    service.append(OWNER_A, conversation.id, role=ConversationRole.USER, content="Apply leave tomorrow")
    service.append(OWNER_A, conversation.id, role=ConversationRole.ASSISTANT, content="Please provide the leave type.")

    reconstructed = RedisAgentConversationStore(service._client)
    restored = reconstructed.get(OWNER_A, conversation.id)
    assert [message.content for message in restored.messages] == ["Apply leave tomorrow", "Please provide the leave type."]
    assert [item.id for item in reconstructed.list(OWNER_A)] == [conversation.id]
    with pytest.raises(ConversationNotFound):
        reconstructed.get(OWNER_B, conversation.id)


def test_pending_state_is_per_conversation_and_clears_without_touching_other_chat():
    service = store()
    first, second = service.create(OWNER_A), service.create(OWNER_A)
    service.set_pending(OWNER_A, first.id, {"start_date": "2026-10-01", "end_date": "2026-10-01"})
    assert service.get(OWNER_A, first.id).pending is not None
    assert service.get(OWNER_A, second.id).pending is None
    service.clear_pending(OWNER_A, first.id)
    assert service.get(OWNER_A, first.id).pending is None


def test_delete_is_owner_scoped_and_removes_the_conversation():
    service = store()
    conversation = service.create(OWNER_A)
    with pytest.raises(ConversationNotFound):
        service.delete(OWNER_B, conversation.id)
    service.delete(OWNER_A, conversation.id)
    with pytest.raises(ConversationNotFound):
        service.get(OWNER_A, conversation.id)
