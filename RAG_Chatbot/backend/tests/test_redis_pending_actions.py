from __future__ import annotations
from datetime import timedelta, datetime, timezone
from threading import Barrier, Thread
from uuid import uuid4
import fakeredis
import pytest
from app.agents.models import ExecutionContext
from app.schemas.agent import PendingActionStatus
from app.services.pending_actions import PendingActionAlreadyConfirmed, PendingActionNotFound, RedisPendingActionStore, to_public

def ctx(conversation=None): return ExecutionContext("EMP001", "Employee", frozenset({"employee"}), "rid", conversation or uuid4(), "EMP001")
def create(store, context): return store.create(context, "request_leave", {"reason":"private","leave_type":"CASUAL"}, {"leave_type":"CASUAL"})

def test_redis_action_round_trip_restart_and_privacy():
    backend=fakeredis.FakeRedis(decode_responses=True); first=RedisPendingActionStore(backend); context=ctx(); action=create(first,context)
    second=RedisPendingActionStore(backend); claimed=second.confirm(action.action_id,context)
    assert claimed.idempotency_key == f"agent-action-{action.action_id}" and claimed.execution_arguments["reason"] == "private"
    assert "reason" not in to_public(claimed).sanitized_arguments

def test_redis_atomic_claim_across_independent_stores():
    backend=fakeredis.FakeRedis(decode_responses=True); context=ctx(); first=RedisPendingActionStore(backend); action=create(first,context); second=RedisPendingActionStore(backend); barrier=Barrier(3); outcomes=[]
    def claim(store):
        barrier.wait()
        try: outcomes.append(store.confirm(action.action_id,context))
        except Exception as exc: outcomes.append(exc)
    left=Thread(target=claim,args=(first,)); right=Thread(target=claim,args=(second,)); left.start(); right.start(); barrier.wait(); left.join(); right.join()
    assert sum(not isinstance(item,Exception) for item in outcomes) == 1
    assert sum(isinstance(item,PendingActionAlreadyConfirmed) for item in outcomes) == 1

def test_redis_claim_rejects_wrong_identity_and_completed_state():
    backend=fakeredis.FakeRedis(decode_responses=True); store=RedisPendingActionStore(backend); context=ctx(); action=create(store,context)
    wrong = ExecutionContext("EMP002", "Other", frozenset({"employee"}), "rid", context.conversation_id, "EMP002")
    with pytest.raises(PendingActionNotFound): store.confirm(action.action_id, wrong)
    store.confirm(action.action_id,context); store.finish(action.action_id,PendingActionStatus.SUCCEEDED)
    with pytest.raises(PendingActionAlreadyConfirmed): store.confirm(action.action_id,context)

def test_redis_stale_execution_recovery_is_atomic_and_keeps_key():
    backend=fakeredis.FakeRedis(decode_responses=True); context=ctx(); first=RedisPendingActionStore(backend, execution_lease=timedelta(seconds=1)); action=create(first,context); claimed=first.confirm(action.action_id,context)
    stale=claimed.model_copy(update={"execution_started_at": datetime(2000,1,1,tzinfo=timezone.utc)})
    backend.set(first._key(action.action_id), first._dump(stale), keepttl=True)
    second=RedisPendingActionStore(backend, execution_lease=timedelta(seconds=1)); recovered=second.confirm(action.action_id,context)
    assert recovered.idempotency_key == action.idempotency_key
    with pytest.raises(PendingActionAlreadyConfirmed): first.confirm(action.action_id,context)
