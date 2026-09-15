"""Trust-boundary tests for the InfoTech-only policy-QA endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import jwt

from app.core.config import get_settings
from app.core.ems_auth import EMSIdentityVerifier
from app.rag.index_lifecycle import IndexStatus
from app.schemas.rag import RAGAnswer, SourceCitation


TEST_SECRET = "ems-test-secret-not-for-production-32-bytes"
EMPLOYEE_ID = UUID("12345678-1234-5678-1234-567812345678")


class PolicyRAG:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def answer(self, question: str) -> RAGAnswer:
        self.questions.append(question)
        if question == "unknown policy":
            return RAGAnswer(
                answer="The available company knowledge does not contain enough information to answer that question.",
                sources=[],
            )
        return RAGAnswer(
            answer="Medical leave is described in the policy.",
            sources=[SourceCitation(document="XYZ_Leave_Attendance_Policy.pdf", page=4, section="Medical Leave")],
        )


def ems_token(subject: str | None = None, *, expired: bool = False, secret: str = TEST_SECRET) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": subject or str(EMPLOYEE_ID), "exp": now - timedelta(minutes=1) if expired else now + timedelta(minutes=5)},
        secret,
        algorithm="HS256",
    )


def configure_infotech_boundary(client, rag: PolicyRAG | None = None) -> PolicyRAG:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/v1/auth/me":
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "id": str(EMPLOYEE_ID),
                "employee_code": "INF1001",
                "full_name": "InfoTech Employee",
                "role": "EMPLOYEE",
                "is_active": True,
            },
        )

    settings = get_settings()
    client.app.state.ems_identity_verifier = EMSIdentityVerifier(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    policy_rag = rag or PolicyRAG()
    client.app.state.rag_service = policy_rag
    client.app.state.rag_index_status = IndexStatus(available=True)
    return policy_rag


def headers(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or ems_token()}"}


def test_infotech_policy_query_uses_verified_ems_identity_and_preserves_citations(client):
    rag = configure_infotech_boundary(client)
    response = client.post("/api/v1/agent/query", json={"message": "What is medical leave?"}, headers=headers())
    assert response.status_code == 200
    assert rag.questions == ["What is medical leave?"]
    assert response.json()["sources"] == [{"document": "XYZ_Leave_Attendance_Policy.pdf", "page": 4, "section": "Medical Leave", "subsection": None}]
    assert response.json()["conversation_id"]


def test_infotech_policy_query_rejects_missing_or_invalid_ems_tokens(client):
    configure_infotech_boundary(client)
    missing = client.post("/api/v1/agent/query", json={"message": "policy"})
    malformed = client.post("/api/v1/agent/query", json={"message": "policy"}, headers=headers("not-a-token"))
    bad_signature = client.post("/api/v1/agent/query", json={"message": "policy"}, headers=headers(ems_token(secret="different-test-secret-not-for-production")))
    expired = client.post("/api/v1/agent/query", json={"message": "policy"}, headers=headers(ems_token(expired=True)))
    malformed_subject = client.post("/api/v1/agent/query", json={"message": "policy"}, headers=headers(ems_token("not-a-uuid")))
    assert [item.status_code for item in (missing, malformed, bad_signature, expired, malformed_subject)] == [401, 401, 401, 401, 401]


def test_infotech_policy_query_rejects_frontend_identity_or_role_overrides(client):
    rag = configure_infotech_boundary(client)
    for field, value in (("employee_id", str(uuid4())), ("role", "ADMIN"), ("manager_id", str(uuid4()))):
        response = client.post("/api/v1/agent/query", json={"message": "policy", field: value}, headers=headers())
        assert response.status_code == 422
    assert rag.questions == []


def test_infotech_policy_query_isolated_from_legacy_actions_and_supports_no_evidence(client):
    rag = configure_infotech_boundary(client)
    action = client.post(
        "/api/v1/agent/query",
        json={"message": "Apply leave from 2026-10-01 to 2026-10-02"},
        headers=headers(),
    )
    no_evidence = client.post("/api/v1/agent/query", json={"message": "unknown policy"}, headers=headers())
    assert action.status_code == 200
    assert "cannot perform workforce actions" in action.json()["answer"]
    assert action.json()["sources"] == []
    assert rag.questions == ["unknown policy"]
    assert no_evidence.status_code == 200
    assert no_evidence.json()["sources"] == []
    assert "does not contain enough information" in no_evidence.json()["answer"]


def test_infotech_policy_query_fails_safely_without_a_valid_index(client):
    rag = configure_infotech_boundary(client)
    client.app.state.rag_index_status = IndexStatus(available=False, reason="manifest missing")
    response = client.post("/api/v1/agent/query", json={"message": "policy"}, headers=headers())
    assert response.status_code == 503
    assert rag.questions == []
    assert "offline index build" in response.json()["error"]["message"]


def test_assistant_proxy_token_cannot_authenticate_infotech_policy_query(client, monkeypatch):
    configure_infotech_boundary(client)
    monkeypatch.setenv("ASSISTANT_PROXY_JWT_SECRET", TEST_SECRET)
    proxy = jwt.encode(
        {"sub": "EMP001", "employee_id": "EMP001", "name": "Legacy", "token_type": "assistant", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        TEST_SECRET,
        algorithm="HS256",
    )
    response = client.post("/api/v1/agent/query", json={"message": "policy"}, headers=headers(proxy))
    assert response.status_code == 401
