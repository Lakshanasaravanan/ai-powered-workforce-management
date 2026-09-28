from __future__ import annotations

from datetime import timedelta
from threading import Barrier, Thread
from uuid import UUID, uuid4

import fakeredis
import pytest
import redis

from app.services.infotech_pending_actions import (
    InfoTechActionName,
    InfoTechActionState,
    PendingActionExpired,
    PendingActionMalformed,
    PendingActionStateError,
    PendingActionStoreUnavailable,
    PendingActionUnavailable,
    RedisInfoTechPendingActionStore,
    UnavailableInfoTechPendingActionStore,
    to_public,
)


ACTOR = UUID("11111111-1111-1111-1111-111111111111")
CONVERSATION = UUID("22222222-2222-2222-2222-222222222222")


def make_store(*, ttl: timedelta = timedelta(minutes=5)) -> RedisInfoTechPendingActionStore:
    return RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True), ttl=ttl)


def create(store: RedisInfoTechPendingActionStore):
    return store.create(
        actor_employee_id=ACTOR,
        conversation_id=CONVERSATION,
        tool_name=InfoTechActionName.APPLY_LEAVE,
        validated_arguments={"leave_type": "CASUAL", "reason": "private medical detail"},
        safe_display={"leave_type": "CASUAL", "dates": ["2027-01-05"]},
    )


def test_action_is_immutable_private_and_uses_server_generated_identifiers():
    store = make_store()
    arguments = {"leave_type": "CASUAL", "reason": "private medical detail"}
    action = store.create(
        actor_employee_id=ACTOR,
        conversation_id=CONVERSATION,
        tool_name=InfoTechActionName.APPLY_LEAVE,
        validated_arguments=arguments,
        safe_display={"leave_type": "CASUAL"},
    )
    arguments["reason"] = "changed after validation"
    public = to_public(action).model_dump(mode="json")
    assert action.action_id and len(action.idempotency_key) >= 32
    assert action.validated_arguments["reason"] == "private medical detail"
    assert "reason" not in public["safe_display"]
    assert "idempotency_key" not in public and "validated_arguments_json" not in public
    with pytest.raises(Exception):
        action.state = InfoTechActionState.CANCELLED


def test_bound_claim_cancel_and_terminal_state_rules():
    store = make_store()
    action = create(store)
    with pytest.raises(PendingActionUnavailable):
        store.claim(action.action_id, uuid4(), CONVERSATION)
    with pytest.raises(PendingActionUnavailable):
        store.cancel(action.action_id, ACTOR, uuid4())
    cancelled = store.cancel(action.action_id, ACTOR, CONVERSATION)
    assert cancelled.state is InfoTechActionState.CANCELLED
    with pytest.raises(PendingActionStateError):
        store.claim(action.action_id, ACTOR, CONVERSATION)


def test_claim_then_nonexecuting_terminal_transition_preserves_idempotency_key():
    store = make_store()
    action = create(store)
    claimed = store.claim(action.action_id, ACTOR, CONVERSATION)
    finished = store.finish_validated_not_executed(action.action_id, ACTOR, CONVERSATION)
    assert claimed.state is InfoTechActionState.EXECUTING
    assert finished.state is InfoTechActionState.VALIDATED_NOT_EXECUTED
    assert finished.idempotency_key == action.idempotency_key
    with pytest.raises(PendingActionStateError):
        store.finish_validated_not_executed(action.action_id, ACTOR, CONVERSATION)


def test_expired_and_malformed_records_fail_closed():
    expired_store = make_store(ttl=timedelta(seconds=-1))
    expired = create(expired_store)
    with pytest.raises(PendingActionExpired):
        expired_store.claim(expired.action_id, ACTOR, CONVERSATION)

    store = make_store()
    malformed_id = uuid4()
    store._client.set(store._key(malformed_id), "not-json", ex=60)
    with pytest.raises(PendingActionMalformed):
        store.claim(malformed_id, ACTOR, CONVERSATION)
    with pytest.raises(Exception):
        store.create(
            actor_employee_id=ACTOR,
            conversation_id=CONVERSATION,
            tool_name="unknown_action",  # type: ignore[arg-type]
            validated_arguments={},
            safe_display={},
        )


def test_atomic_claim_allows_exactly_one_independent_store():
    backend = fakeredis.FakeRedis(decode_responses=True)
    first = RedisInfoTechPendingActionStore(backend)
    second = RedisInfoTechPendingActionStore(backend)
    action = create(first)
    barrier = Barrier(3)
    outcomes: list[object] = []

    def claim(store: RedisInfoTechPendingActionStore) -> None:
        barrier.wait()
        try:
            outcomes.append(store.claim(action.action_id, ACTOR, CONVERSATION))
        except Exception as exc:  # expected loser outcome
            outcomes.append(exc)

    left, right = Thread(target=claim, args=(first,)), Thread(target=claim, args=(second,))
    left.start()
    right.start()
    barrier.wait()
    left.join()
    right.join()
    assert sum(getattr(item, "state", None) is InfoTechActionState.EXECUTING for item in outcomes) == 1
    assert sum(isinstance(item, PendingActionStateError) for item in outcomes) == 1


class DownRedis:
    def set(self, *args, **kwargs):
        raise redis.ConnectionError("unavailable")


def test_redis_failure_and_disabled_store_never_fall_back_to_memory():
    store = RedisInfoTechPendingActionStore(DownRedis())
    with pytest.raises(PendingActionStoreUnavailable):
        create(store)
    with pytest.raises(PendingActionStoreUnavailable):
        UnavailableInfoTechPendingActionStore().claim(uuid4(), ACTOR, CONVERSATION)
