from __future__ import annotations

from uuid import UUID

from app.rag.service import RAGServiceError
from app.schemas.rag import RAGAnswer, SourceCitation


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["environment"] == "test"


def test_request_id_is_generated_and_returned(client):
    response = client.get("/health")
    assert UUID(response.headers["X-Request-ID"])


def test_valid_request_id_is_preserved(client):
    supplied_id = "d4e2f11d-0fd5-4a61-979c-38af526c4a85"
    response = client.get("/health", headers={"X-Request-ID": supplied_id})
    assert response.headers["X-Request-ID"] == supplied_id


def test_chat_requires_authenticated_identity(client):
    response = client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 401
    assert response.json()["error"]["request_id"]


def test_chat_placeholder_and_conversation_id(client, auth_headers):
    class NoEvidenceRAGService:
        def answer(self, question):
            return RAGAnswer(
                answer="The available company knowledge does not contain enough information to answer that question.",
                sources=[],
            )

    client.app.state.rag_service = NoEvidenceRAGService()
    response = client.post("/api/v1/chat", json={"message": "Hello"}, headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "does not contain enough information" in payload["answer"]
    assert payload["sources"] == []
    assert UUID(payload["conversation_id"])


def test_chat_validation_is_structured(client, auth_headers):
    response = client.post("/api/v1/chat", json={"message": "  "}, headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["request_id"]


def test_mock_authentication_issues_and_verifies_token(client):
    class NoEvidenceRAGService:
        def answer(self, question):
            return RAGAnswer(
                answer="The available company knowledge does not contain enough information to answer that question.",
                sources=[],
            )

    client.app.state.rag_service = NoEvidenceRAGService()
    token_response = client.post(
        "/api/v1/auth/token", json={"username": "emp002", "password": "demo-emp002"}
    )
    assert token_response.status_code == 200
    chat_response = client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )
    assert chat_response.status_code == 200


def test_invalid_mock_credentials_are_rejected(client):
    response = client.post("/api/v1/auth/token", json={"username": "EMP001", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid credentials"


def test_chat_returns_mocked_rag_answer_and_citations(client, auth_headers):
    class MockRAGService:
        def answer(self, question):
            return RAGAnswer(
                answer="Medical leave is available under the leave policy.",
                sources=[SourceCitation(document="XYZ_Leave_Attendance_Policy.pdf", page=4, section="Medical Leave")],
            )

    client.app.state.rag_service = MockRAGService()
    response = client.post("/api/v1/chat", json={"message": "What is medical leave?"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["sources"] == [{"document": "XYZ_Leave_Attendance_Policy.pdf", "page": 4, "section": "Medical Leave", "subsection": None}]


def test_chat_returns_safe_service_error(client, auth_headers):
    class FailingRAGService:
        def answer(self, question):
            raise RAGServiceError("provider failure")

    client.app.state.rag_service = FailingRAGService()
    response = client.post("/api/v1/chat", json={"message": "What is medical leave?"}, headers=auth_headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rag_service_unavailable"
