"""Endpoint integration for deterministic InfoTech read intent routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import jwt

from app.core.config import get_settings
from app.core.ems_auth import EMSIdentityVerifier
from app.rag.index_lifecycle import IndexStatus
from app.schemas.rag import RAGAnswer, SourceCitation
from app.services.infotech_ems import InfoTechEMSReadClient
from app.tools.infotech_ems import build_infotech_read_registry


EMPLOYEE_ID = UUID("12345678-1234-5678-1234-567812345678")
SECRET = "ems-test-secret-not-for-production-32-bytes"


class RecordingRAG:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def answer(self, question: str) -> RAGAnswer:
        self.questions.append(question)
        return RAGAnswer(answer="Policy answer", sources=[SourceCitation(document="XYZ_Leave_Attendance_Policy.pdf", page=1)])


def token() -> str:
    return jwt.encode({"sub": str(EMPLOYEE_ID), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET, algorithm="HS256")


def employee_payload(role: str) -> dict[str, object]:
    return {
        "id": str(EMPLOYEE_ID), "employee_code": "INF1001", "full_name": "Test Employee",
        "company_email": "INF1001@infotech.local", "role": role, "designation": "Engineer",
        "department": "Engineering", "manager_id": None, "is_active": True,
    }


def configure(client, *, role="EMPLOYEE", read_status=200):
    def identity_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/me"
        return httpx.Response(200, json={**employee_payload(role)})

    read_requests: list[httpx.Request] = []

    def read_handler(request: httpx.Request) -> httpx.Response:
        read_requests.append(request)
        if read_status != 200:
            return httpx.Response(read_status, json={"detail": "safe"})
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(200, json=employee_payload(role))
        if request.url.path == "/api/v1/notifications/unread-count":
            return httpx.Response(200, json={"unread_count": 2})
        if request.url.path in {"/api/v1/leaves/me", "/api/v1/notifications", "/api/v1/leaves/team", "/api/v1/employees/me/direct-reports"}:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    settings = get_settings()
    client.app.state.ems_identity_verifier = EMSIdentityVerifier(settings, client=httpx.Client(transport=httpx.MockTransport(identity_handler)))
    client.app.state.infotech_read_registry = build_infotech_read_registry(
        InfoTechEMSReadClient(settings, httpx.Client(transport=httpx.MockTransport(read_handler)))
    )
    rag = RecordingRAG()
    client.app.state.rag_service = rag
    client.app.state.rag_index_status = IndexStatus(available=True)
    return rag, read_requests


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}"}


def test_read_endpoint_forwards_current_bearer_and_skips_rag(client):
    rag, requests = configure(client)
    conversation_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    response = client.post("/api/v1/agent/query", json={"message": "show my profile", "conversation_id": conversation_id}, headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == [] and body["conversation_id"] == conversation_id and body["response_type"] == "message"
    assert "INF1001" in body["answer"] and rag.questions == []
    assert len(requests) == 1 and requests[0].url.path == "/api/v1/auth/me"
    assert requests[0].headers["Authorization"].startswith("Bearer ")


def test_personal_read_and_manager_role_rejection_do_not_require_rag(client):
    rag, requests = configure(client, role="EMPLOYEE")
    personal = client.post("/api/v1/agent/query", json={"message": "how many unread notifications do I have"}, headers=headers())
    denied = client.post("/api/v1/agent/query", json={"message": "show my team leaves"}, headers=headers())
    assert personal.status_code == denied.status_code == 200
    assert "2 unread" in personal.json()["answer"]
    assert "only to Managers" in denied.json()["answer"]
    assert len(requests) == 1 and rag.questions == []


def test_policy_remains_grounded_path_while_nonpolicy_intents_do_not_call_rag(client):
    rag, requests = configure(client)
    policy = client.post("/api/v1/agent/query", json={"message": "What is casual leave?"}, headers=headers())
    unsupported = client.post("/api/v1/agent/query", json={"message": "what is my leave balance?"}, headers=headers())
    mutation = client.post("/api/v1/agent/query", json={"message": "apply casual leave tomorrow"}, headers=headers())
    confirmation = client.post("/api/v1/agent/query", json={"message": "confirm"}, headers=headers())
    cancellation = client.post("/api/v1/agent/query", json={"message": "cancel that"}, headers=headers())
    assert policy.json()["sources"] and rag.questions == ["What is casual leave?"]
    assert "authoritative entitlement" in unsupported.json()["answer"]
    assert mutation.json()["response_type"] == "clarification"
    assert "reason" in mutation.json()["answer"].lower()
    assert "no executable pending action" in confirmation.json()["answer"]
    assert "no pending action" in cancellation.json()["answer"]
    assert requests == []


def test_ems_error_is_safe_and_identity_fields_remain_rejected(client):
    rag, _ = configure(client, read_status=503)
    failed = client.post("/api/v1/agent/query", json={"message": "show my profile"}, headers=headers())
    injected = client.post("/api/v1/agent/query", json={"message": "show my profile", "employee_id": str(EMPLOYEE_ID)}, headers=headers())
    assert failed.status_code == 200 and "temporarily unavailable" in failed.json()["answer"]
    assert injected.status_code == 422 and rag.questions == []
