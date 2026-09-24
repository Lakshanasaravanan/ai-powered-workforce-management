"""Step 5A manager-decision references and proposal-only safety tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import fakeredis
import httpx
import jwt

from app.core.config import get_settings
from app.core.ems_auth import EMSIdentityVerifier
from app.services.infotech_decision_references import RedisInfoTechDecisionReferenceStore
from app.services.infotech_ems import InfoTechEMSReadClient
from app.services.infotech_pending_actions import (
    InfoTechActionName,
    InfoTechActionState,
    RedisInfoTechPendingActionStore,
)
from app.tools.infotech_ems import build_infotech_read_registry


MANAGER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_MANAGER_ID = UUID("22222222-2222-2222-2222-222222222222")
EMPLOYEE_ID = UUID("33333333-3333-3333-3333-333333333333")
INDIRECT_EMPLOYEE_ID = UUID("44444444-4444-4444-4444-444444444444")
LEAVE_ID = UUID("55555555-5555-5555-5555-555555555555")
MEDICAL_ID = UUID("66666666-6666-6666-6666-666666666666")
CONVERSATION_ID = UUID("77777777-7777-7777-7777-777777777777")
OTHER_CONVERSATION_ID = UUID("88888888-8888-8888-8888-888888888888")
SECRET = "ems-test-secret-not-for-production-32-bytes"


def bearer(employee_id: UUID) -> dict[str, str]:
    value = jwt.encode(
        {"sub": str(employee_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {value}"}


def role_for(employee_id: UUID) -> str:
    if employee_id in {MANAGER_ID, OTHER_MANAGER_ID}:
        return "MANAGER"
    if employee_id == EMPLOYEE_ID:
        return "EMPLOYEE"
    return "ADMIN"


def profile(employee_id: UUID) -> dict[str, object]:
    role = role_for(employee_id)
    return {
        "id": str(employee_id), "employee_code": "MGR1001" if role == "MANAGER" else "INF1001",
        "full_name": "Manager One" if role == "MANAGER" else "Employee One",
        "company_email": "test@infotech.local", "role": role, "designation": "Manager" if role == "MANAGER" else "Engineer",
        "department": "Engineering", "manager_id": None, "is_active": True,
    }


def leave(leave_id: UUID, *, employee_id: UUID = EMPLOYEE_ID, leave_type="CASUAL", status="PENDING", approval_required=True) -> dict[str, object]:
    return {
        "id": str(leave_id),
        "employee": {"id": str(employee_id), "employee_code": "INF1001", "full_name": "Employee One"},
        "leave_type": leave_type, "status": status, "start_date": "2026-10-01", "end_date": "2026-10-01",
        "duration": "FULL_DAY", "half_day_period": None, "reason": "private", "approval_required": approval_required,
        "decided_by_id": None, "decided_at": None, "decision_note": None, "decision_source": None,
        "manager_notification_delivered": True, "created_at": "2026-09-15T10:00:00", "updated_at": "2026-09-15T10:00:00",
    }


def configure(client):
    requests: list[httpx.Request] = []
    leaves = {
        LEAVE_ID: leave(LEAVE_ID),
        MEDICAL_ID: leave(MEDICAL_ID, leave_type="MEDICAL", status="APPROVED", approval_required=False),
        INDIRECT_EMPLOYEE_ID: leave(INDIRECT_EMPLOYEE_ID, employee_id=INDIRECT_EMPLOYEE_ID),
    }

    def identity_handler(request: httpx.Request) -> httpx.Response:
        claims = jwt.decode(request.headers["Authorization"].removeprefix("Bearer "), SECRET, algorithms=["HS256"])
        return httpx.Response(200, json=profile(UUID(claims["sub"])))

    def ems_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"  # Step 5A never calls an EMS mutation.
        if request.url.path == "/api/v1/leaves/team":
            # EMS is authoritative for direct reports: the indirect leave is absent.
            return httpx.Response(200, json=[leaves[LEAVE_ID], leaves[MEDICAL_ID]])
        if request.url.path.startswith("/api/v1/leaves/"):
            try:
                target = UUID(request.url.path.rsplit("/", 1)[-1])
            except ValueError:
                return httpx.Response(404, json={"detail": "missing"})
            record = leaves.get(target)
            return httpx.Response(200, json=record) if record else httpx.Response(404, json={"detail": "missing"})
        return httpx.Response(404, json={"detail": "missing"})

    settings = get_settings()
    ems = InfoTechEMSReadClient(settings, httpx.Client(transport=httpx.MockTransport(ems_handler)))
    client.app.state.ems_identity_verifier = EMSIdentityVerifier(settings, client=httpx.Client(transport=httpx.MockTransport(identity_handler)))
    client.app.state.infotech_ems_client = ems
    client.app.state.infotech_read_registry = build_infotech_read_registry(ems)
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client.app.state.infotech_pending_actions = RedisInfoTechPendingActionStore(redis_client)
    client.app.state.infotech_decision_references = RedisInfoTechDecisionReferenceStore(redis_client)
    return leaves, requests, redis_client


def team_query(client, *, conversation_id=CONVERSATION_ID, actor=MANAGER_ID):
    return client.post(
        "/api/v1/agent/query",
        json={"message": "Show my pending team leave requests", "conversation_id": str(conversation_id)},
        headers=bearer(actor),
    )


def reference_from(response) -> str:
    import re

    match = re.search(r"LR-[A-F0-9]{20}", response.json()["answer"])
    assert match is not None
    return match.group(0)


def test_manager_gets_opaque_reference_only_for_eligible_direct_report_and_can_resolve_it(client):
    _, requests, _ = configure(client)
    response = team_query(client)
    assert response.status_code == 200
    answer = response.json()["answer"]
    reference = reference_from(response)
    assert str(LEAVE_ID) not in answer and str(EMPLOYEE_ID) not in answer and str(INDIRECT_EMPLOYEE_ID) not in answer
    assert "MEDICAL" in answer and answer.count("Reference:") == 1
    assert all(request.method == "GET" for request in requests)
    record = client.app.state.infotech_decision_references.resolve(reference, manager_employee_id=MANAGER_ID, conversation_id=CONVERSATION_ID)
    assert record.leave_id == LEAVE_ID and record.reference == reference
    refreshed = reference_from(team_query(client))
    assert refreshed != reference
    assert client.app.state.infotech_decision_references.resolve(
        refreshed, manager_employee_id=MANAGER_ID, conversation_id=CONVERSATION_ID
    ).leave_id == LEAVE_ID
    # Refreshing identifies the same target again; it does not create authority.
    assert client.app.state.infotech_decision_references.resolve(
        reference, manager_employee_id=MANAGER_ID, conversation_id=CONVERSATION_ID
    ).leave_id == LEAVE_ID


def test_references_fail_closed_for_other_actor_conversation_unknown_tampering_and_expiry(client):
    _, _, redis_client = configure(client)
    reference = reference_from(team_query(client))
    for actor, conversation in ((OTHER_MANAGER_ID, CONVERSATION_ID), (MANAGER_ID, OTHER_CONVERSATION_ID)):
        response = client.post("/api/v1/agent/query", json={"message": f"Approve {reference}", "conversation_id": str(conversation)}, headers=bearer(actor))
        assert response.status_code == 200 and response.json()["response_type"] == "clarification"
    for invalid in ("LR-AAAAAAAAAAAAAAAAAAAA", reference[:-1] + ("A" if reference[-1] != "A" else "B")):
        response = client.post("/api/v1/agent/query", json={"message": f"Approve {invalid}", "conversation_id": str(CONVERSATION_ID)}, headers=bearer(MANAGER_ID))
        assert response.status_code == 200 and response.json()["response_type"] == "clarification"
    client.app.state.infotech_decision_references = RedisInfoTechDecisionReferenceStore(redis_client, ttl=timedelta(seconds=-1))
    expired = client.app.state.infotech_decision_references.issue(manager_employee_id=MANAGER_ID, conversation_id=CONVERSATION_ID, leave_id=LEAVE_ID)
    response = client.post("/api/v1/agent/query", json={"message": f"Approve {expired.reference}", "conversation_id": str(CONVERSATION_ID)}, headers=bearer(MANAGER_ID))
    assert response.status_code == 200 and "expired" in response.json()["answer"].lower()


def test_manager_approve_and_reject_create_immutable_proposals(client):
    _, requests, _ = configure(client)
    reference = reference_from(team_query(client))
    for command, expected_action, note in (
        (f"Approve {reference}", "approve_leave", None),
        (f"Reject {reference} because project coverage is unavailable", "reject_leave", "project coverage is unavailable"),
    ):
        response = client.post("/api/v1/agent/query", json={"message": command, "conversation_id": str(CONVERSATION_ID)}, headers=bearer(MANAGER_ID))
        assert response.status_code == 200
        body = response.json()
        assert body["response_type"] == "action_proposal"
        assert body["action"]["tool_name"] == expected_action
        assert str(LEAVE_ID) not in str(body["action"])
        action_id = UUID(body["action"]["action_id"])
        stored = client.app.state.infotech_pending_actions._load(client.app.state.infotech_pending_actions._client.get(client.app.state.infotech_pending_actions._key(action_id)))
        assert stored.validated_arguments == {"leave_id": str(LEAVE_ID), "decision_note": note}
        assert stored.target_entity_id == LEAVE_ID
    assert requests and all(request.method == "GET" for request in requests)


def test_missing_fuzzy_and_ineligible_targets_never_create_proposals(client):
    leaves, _, _ = configure(client)
    for message in ("Approve leave", "Approve Ravi's leave", "Approve tomorrow's leave", "Approve the casual one"):
        response = client.post("/api/v1/agent/query", json={"message": message, "conversation_id": str(CONVERSATION_ID)}, headers=bearer(MANAGER_ID))
        assert response.status_code == 200 and response.json()["response_type"] == "clarification"
    reference = reference_from(team_query(client))
    leaves[LEAVE_ID] = leave(LEAVE_ID, status="APPROVED", approval_required=True)
    stale = client.post("/api/v1/agent/query", json={"message": f"Approve {reference}", "conversation_id": str(CONVERSATION_ID)}, headers=bearer(MANAGER_ID))
    assert stale.status_code == 200 and stale.json()["response_type"] == "clarification"


def test_employee_and_admin_cannot_issue_or_propose_decisions_and_provider_is_not_used(client):
    _, requests, _ = configure(client)
    for actor in (EMPLOYEE_ID, uuid4()):
        list_response = team_query(client, actor=actor)
        proposal = client.post("/api/v1/agent/query", json={"message": "Approve LR-AAAAAAAAAAAAAAAAAAAA", "conversation_id": str(CONVERSATION_ID)}, headers=bearer(actor))
        assert list_response.status_code == proposal.status_code == 200
        assert "Managers" in list_response.json()["answer"] and "Managers" in proposal.json()["answer"]
    assert requests == []
