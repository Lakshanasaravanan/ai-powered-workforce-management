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


def test_embedding_and_reranker_offline_cache_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "embedding-cache"))
    monkeypatch.setenv("EMBEDDING_LOCAL_FILES_ONLY", "true")
    monkeypatch.setenv("RERANK_CACHE_DIR", str(tmp_path / "rerank-cache"))
    monkeypatch.setenv("RERANK_LOCAL_FILES_ONLY", "true")
    settings = Settings(_env_file=None)
    assert settings.embedding_cache_dir == tmp_path / "embedding-cache"
    assert settings.embedding_local_files_only is True
    assert settings.rerank_cache_dir == tmp_path / "rerank-cache"
    assert settings.rerank_local_files_only is True


def test_embedding_device_defaults_to_cpu_and_can_be_configured(monkeypatch: pytest.MonkeyPatch):
    assert Settings(_env_file=None).embedding_device == "cpu"
    monkeypatch.setenv("EMBEDDING_DEVICE", "mps")
    assert Settings(_env_file=None).embedding_device == "mps"
