from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_loads_environment_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "configured-test-secret")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    settings = Settings()
    assert settings.environment == "development"
    assert settings.llm_provider == "openrouter"
    assert settings.jwt_signing_key == "configured-test-secret"


def test_production_requires_explicit_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
