"""Centralized, secret-safe application configuration."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Settings sourced from environment variables and a local .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    llm_provider: str | None = None
    llm_api_key: SecretStr | None = None
    llm_base_url: AnyHttpUrl | None = None
    llm_model: str | None = None
    qdrant_url: AnyHttpUrl | None = None
    qdrant_api_key: SecretStr | None = None
    redis_url: str | None = None

    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=60, ge=1, le=1440)

    _ephemeral_jwt_secret: str | None = None

    @model_validator(mode="after")
    def require_secret_in_non_development(self) -> "Settings":
        if self.environment in {"staging", "production"} and self.jwt_secret_key is None:
            raise ValueError("JWT_SECRET_KEY must be configured outside development and test")
        return self

    @property
    def jwt_signing_key(self) -> str:
        """Return configured key, or a process-local development key without logging it."""
        if self.jwt_secret_key is not None:
            return self.jwt_secret_key.get_secret_value()
        if self._ephemeral_jwt_secret is None:
            self._ephemeral_jwt_secret = secrets.token_urlsafe(48)
        return self._ephemeral_jwt_secret

    @property
    def readiness_warnings(self) -> list[str]:
        if self.jwt_secret_key is None:
            return ["JWT_SECRET_KEY is not configured; using an ephemeral development signing key"]
        return []


@lru_cache
def get_settings() -> Settings:
    """Return one settings instance per process to avoid repeated environment parsing."""
    return Settings()
