from __future__ import annotations

from uuid import UUID


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
    response = client.post("/api/v1/chat", json={"message": "Hello"}, headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "foundation is ready" in payload["answer"]
    assert UUID(payload["conversation_id"])


def test_chat_validation_is_structured(client, auth_headers):
    response = client.post("/api/v1/chat", json={"message": "  "}, headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["request_id"]


def test_mock_authentication_issues_and_verifies_token(client):
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
