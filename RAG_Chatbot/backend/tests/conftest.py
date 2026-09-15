from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def test_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-not-for-production-32-bytes-minimum")
    monkeypatch.setenv("EMS_JWT_SECRET", "ems-test-secret-not-for-production-32-bytes")
    monkeypatch.setenv("EMS_API_BASE_URL", "http://ems.test")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/token", json={"username": "EMP001", "password": "demo-emp001"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
