from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import fakeredis
import httpx
import jwt

from app.core.config import get_settings
from app.core.ems_auth import EMSIdentityVerifier
from app.services.infotech_pending_actions import (
    InfoTechActionName,
    InfoTechActionState,
    NonExecutingActionExecutor,
    RedisInfoTechPendingActionStore,
)


EMPLOYEE_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_EMPLOYEE_ID = UUID("44444444-4444-4444-4444-444444444444")
CONVERSATION_ID = UUID("55555555-5555-5555-5555-555555555555")
SECRET = "ems-test-secret-not-for-production-32-bytes"


class MustNotRunRAG:
    def answer(self, question: str):  # pragma: no cover - assertion is the absence of this call
        raise AssertionError("confirmation endpoints must not invoke RAG")


class RecordingApplyLeave:
    def __init__(self): self.calls = []
    def apply_leave(self, leave, bearer_token, idempotency_key, correlation_id):
        self.calls.append((leave, bearer_token, idempotency_key, correlation_id))
        return object()

    def approve_leave(self, leave, bearer_token, idempotency_key, correlation_id):
        self.calls.append(("approve", leave, bearer_token, idempotency_key, correlation_id))
        return object()

    def reject_leave(self, leave, bearer_token, idempotency_key, correlation_id):
        self.calls.append(("reject", leave, bearer_token, idempotency_key, correlation_id))
        return object()


def bearer(employee_id: UUID = EMPLOYEE_ID) -> dict[str, str]:
    token = jwt.encode(
        {"sub": str(employee_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def configure(client) -> RedisInfoTechPendingActionStore:
    def identity_handler(request: httpx.Request) -> httpx.Response:
        claims = jwt.decode(request.headers["Authorization"].removeprefix("Bearer "), SECRET, algorithms=["HS256"])
        employee_id = UUID(claims["sub"])
        return httpx.Response(
            200,
            json={
                "id": str(employee_id),
                "employee_code": "INF2001",
                "full_name": "Action Test Employee",
                "role": "EMPLOYEE",
                "is_active": True,
            },
        )

    settings = get_settings()
    client.app.state.ems_identity_verifier = EMSIdentityVerifier(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(identity_handler)),
    )
    store = RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True))
    client.app.state.infotech_pending_actions = store
    client.app.state.infotech_pending_executor = NonExecutingActionExecutor()
    client.app.state.infotech_ems_client = RecordingApplyLeave()
    client.app.state.rag_service = MustNotRunRAG()
    return store


def create(store: RedisInfoTechPendingActionStore, *, ttl: timedelta | None = None):
    if ttl is not None:
        store._ttl = ttl
    return store.create(
        actor_employee_id=EMPLOYEE_ID,
        conversation_id=CONVERSATION_ID,
        tool_name=InfoTechActionName.APPLY_LEAVE,
        validated_arguments={"leave_type": "CASUAL", "start_date": "2027-01-05", "end_date": "2027-01-05", "duration": "FULL_DAY", "half_day_period": None, "reason": "private detail"},
        safe_display={"leave_type": "CASUAL", "dates": ["2027-01-05"]},
    )


def create_decision(store: RedisInfoTechPendingActionStore, action_name: InfoTechActionName):
    return store.create(
        actor_employee_id=EMPLOYEE_ID, conversation_id=CONVERSATION_ID, tool_name=action_name,
        validated_arguments={"leave_id": str(uuid4()), "decision_note": "coverage"},
        safe_display={"title": "Leave decision"}, target_entity_id=uuid4(),
    )


def test_confirm_is_authenticated_bound_nonexecuting_and_idempotent(client):
    store = configure(client)
    action = create(store)
    response = client.post(
        f"/api/v1/agent/actions/{action.action_id}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)},
        headers=bearer(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action_id"] == str(action.action_id)
    assert body["state"] == InfoTechActionState.SUCCEEDED
    assert "submitted" in body["message"]
    assert "reason" not in str(body).lower()
    stored = store._load(store._client.get(store._key(action.action_id)))
    assert stored.state is InfoTechActionState.SUCCEEDED
    assert stored.idempotency_key == action.idempotency_key
    replay = client.post(
        f"/api/v1/agent/actions/{action.action_id}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer(),
    )
    assert replay.status_code == 409


def test_explicit_date_query_prepares_before_the_typed_ems_confirmation(client):
    store = configure(client)
    recorder = client.app.state.infotech_ems_client
    response = client.post(
        "/api/v1/agent/query",
        json={
            "message": "Apply for casual leave on September 25, 2026 because of a family visit.",
            "conversation_id": str(CONVERSATION_ID),
        },
        headers=bearer(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["response_type"] == "action_proposal"
    assert body["action"]["safe_display"]["date"] == "2026-09-25"
    assert recorder.calls == []
    action_id = body["action"]["action_id"]
    confirmed = client.post(
        f"/api/v1/agent/actions/{action_id}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)},
        headers=bearer(),
    )
    assert confirmed.status_code == 200
    assert len(recorder.calls) == 1
    stored = store._load(store._client.get(store._key(UUID(action_id))))
    assert stored.tool_name is InfoTechActionName.APPLY_LEAVE


def test_cancel_and_privacy_boundaries_reject_unsafe_inputs(client):
    store = configure(client)
    action = create(store)
    wrong_employee = client.post(
        f"/api/v1/agent/actions/{action.action_id}/cancel",
        json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer(OTHER_EMPLOYEE_ID),
    )
    wrong_conversation = client.post(
        f"/api/v1/agent/actions/{action.action_id}/cancel",
        json={"conversation_id": str(uuid4())}, headers=bearer(),
    )
    assert wrong_employee.status_code == wrong_conversation.status_code == 404
    rejected_fields = client.post(
        f"/api/v1/agent/actions/{action.action_id}/cancel",
        json={
            "conversation_id": str(CONVERSATION_ID),
            "employee_id": str(OTHER_EMPLOYEE_ID),
            "arguments": {"reason": "replace"},
            "idempotency_key": "replace",
        },
        headers=bearer(),
    )
    assert rejected_fields.status_code == 422
    cancelled = client.post(
        f"/api/v1/agent/actions/{action.action_id}/cancel",
        json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer(),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == InfoTechActionState.CANCELLED
    assert client.post(
        f"/api/v1/agent/actions/{action.action_id}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer(),
    ).status_code == 409


def test_confirm_rejects_unauthenticated_expired_and_unknown_actions(client):
    store = configure(client)
    action = create(store, ttl=timedelta(seconds=-1))
    expired = client.post(
        f"/api/v1/agent/actions/{action.action_id}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer(),
    )
    assert expired.status_code == 409
    assert client.post(
        f"/api/v1/agent/actions/{uuid4()}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer(),
    ).status_code == 404
    assert client.post(
        f"/api/v1/agent/actions/{uuid4()}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)},
    ).status_code == 401


def test_action_contract_rejects_invalid_bearers_and_all_client_controlled_action_fields(client):
    store = configure(client)
    action = create(store)
    invalid = client.post(
        f"/api/v1/agent/actions/{action.action_id}/confirm",
        json={"conversation_id": str(CONVERSATION_ID)},
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert invalid.status_code == 401
    rejected = client.post(
        f"/api/v1/agent/actions/{action.action_id}/confirm",
        json={
            "conversation_id": str(CONVERSATION_ID),
            "tool_name": "apply_leave",
            "employee_id": str(OTHER_EMPLOYEE_ID),
            "role": "ADMIN",
            "manager_id": str(OTHER_EMPLOYEE_ID),
            "target_employee": str(OTHER_EMPLOYEE_ID),
            "idempotency_key": "replace",
            "bearer": "replace",
            "ems_url": "https://example.invalid",
            "arguments": {"reason": "replace"},
        },
        headers=bearer(),
    )
    assert rejected.status_code == 422


def test_confirm_executes_only_stored_approve_or_reject_decision_without_rag(client):
    store = configure(client)
    recorder = client.app.state.infotech_ems_client
    for action_name, expected in ((InfoTechActionName.APPROVE_LEAVE, "approve"), (InfoTechActionName.REJECT_LEAVE, "reject")):
        action = create_decision(store, action_name)
        result = client.post(f"/api/v1/agent/actions/{action.action_id}/confirm", json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer())
        assert result.status_code == 200 and result.json()["state"] == "succeeded"
        assert recorder.calls[-1][0] == expected
        stored = store._load(store._client.get(store._key(action.action_id)))
        assert stored.state is InfoTechActionState.SUCCEEDED and stored.idempotency_key == action.idempotency_key


def test_cancelled_or_expired_decision_never_reaches_ems(client):
    store = configure(client)
    recorder = client.app.state.infotech_ems_client
    cancelled = create_decision(store, InfoTechActionName.APPROVE_LEAVE)
    assert client.post(f"/api/v1/agent/actions/{cancelled.action_id}/cancel", json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer()).status_code == 200
    assert client.post(f"/api/v1/agent/actions/{cancelled.action_id}/confirm", json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer()).status_code == 409
    store._ttl = timedelta(seconds=-1)
    expired = create_decision(store, InfoTechActionName.REJECT_LEAVE)
    assert client.post(f"/api/v1/agent/actions/{expired.action_id}/confirm", json={"conversation_id": str(CONVERSATION_ID)}, headers=bearer()).status_code == 409
    assert recorder.calls == []
