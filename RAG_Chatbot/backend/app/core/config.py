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

    llm_provider: Literal["openrouter", "ollama"] = "openrouter"
    llm_api_key: SecretStr | None = None
    llm_base_url: AnyHttpUrl | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    ollama_base_url: AnyHttpUrl | None = None
    ollama_model: str | None = None
    qdrant_url: AnyHttpUrl | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "infotech-policy"
    vector_store_backend: Literal["faiss", "qdrant"] = "faiss"
    vector_store_dimension: int = Field(default=384, ge=1, le=8192)
    redis_url: str | None = None
    redis_enabled: bool = False
    pending_action_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    pending_action_execution_lease_seconds: int = Field(default=60, ge=5, le=900)
    chat_rate_limit_per_minute: int = Field(default=30, ge=1, le=1000)
    confirmation_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: Literal["cpu", "mps", "cuda"] = "cpu"
    embedding_cache_dir: Path | None = None
    embedding_local_files_only: bool = False
    rag_chunk_size: int = Field(default=450, ge=64, le=4096)
    rag_chunk_overlap: int = Field(default=60, ge=0, le=1024)
    rag_min_chunk_tokens: int = Field(default=24, ge=1, le=1024)
    rag_retrieval_top_k: int = Field(default=5, ge=1, le=50)
    rag_retrieval_candidate_k: int = Field(default=30, ge=1, le=200)
    rag_hybrid_enabled: bool = False
    rag_rrf_k: int = Field(default=60, ge=1, le=500)
    rag_rerank_enabled: bool = False
    rag_rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_cache_dir: Path | None = None
    rerank_local_files_only: bool = False
    rag_max_context_tokens: int = Field(default=1800, ge=128, le=16000)

    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=60, ge=1, le=1440)
    development_auth_enabled: bool = True
    assistant_proxy_jwt_secret: SecretStr | None = None
    assistant_proxy_issuer: str = "slams-assistant-proxy"
    assistant_proxy_audience: str = "agentic-rag-assistant"

    # InfoTech EMS is the authority for the new policy-QA API.  These are kept
    # distinct from the legacy service's development and SLAMS credentials.
    ems_jwt_secret: SecretStr | None = None
    ems_jwt_algorithm: Literal["HS256"] = "HS256"
    ems_api_base_url: AnyHttpUrl | None = None
    ems_auth_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    cors_allowed_origins: str = "http://localhost:5173"

    slams_enabled: bool = False
    slams_base_url: AnyHttpUrl | None = None
    slams_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    slams_read_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    slams_delegation_issuer: str | None = None
    slams_delegation_audience: str | None = None
    slams_delegation_private_key: SecretStr | None = None
    slams_delegation_token_ttl_seconds: int = Field(default=300, ge=30, le=900)

    _ephemeral_jwt_secret: str | None = None

    @model_validator(mode="after")
    def require_secret_in_non_development(self) -> "Settings":
        def unsafe(value: SecretStr | None) -> bool:
            if value is None:
                return True
            normalized = value.get_secret_value().strip().lower()
            return not normalized or "replace-with" in normalized or "change-me" in normalized
        if self.environment in {"staging", "production"}:
            if unsafe(self.jwt_secret_key):
                raise ValueError("JWT_SECRET_KEY must be a non-placeholder secret outside development and test")
            if self.development_auth_enabled:
                raise ValueError("DEVELOPMENT_AUTH_ENABLED must be false outside development and test")
            if unsafe(self.assistant_proxy_jwt_secret):
                raise ValueError("ASSISTANT_PROXY_JWT_SECRET must be a non-placeholder secret outside development and test")
            if self.llm_provider == "openrouter" and (not self.llm_api_key or self.llm_base_url is None or not self.llm_model):
                raise ValueError("LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL are required for OpenRouter outside development and test")
            if self.llm_provider == "ollama" and (self.ollama_base_url is None or not self.ollama_model):
                raise ValueError("OLLAMA_BASE_URL and OLLAMA_MODEL are required for Ollama outside development and test")
            if unsafe(self.ems_jwt_secret) or self.ems_api_base_url is None:
                raise ValueError("EMS_JWT_SECRET and EMS_API_BASE_URL are required outside development and test")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        if self.rag_min_chunk_tokens > self.rag_chunk_size:
            raise ValueError("RAG_MIN_CHUNK_TOKENS must not exceed RAG_CHUNK_SIZE")
        if self.rag_retrieval_candidate_k < self.rag_retrieval_top_k:
            raise ValueError("RAG_RETRIEVAL_CANDIDATE_K must be at least RAG_RETRIEVAL_TOP_K")
        if self.slams_enabled:
            required = {
                "SLAMS_BASE_URL": self.slams_base_url,
                "SLAMS_DELEGATION_ISSUER": self.slams_delegation_issuer,
                "SLAMS_DELEGATION_AUDIENCE": self.slams_delegation_audience,
                "SLAMS_DELEGATION_PRIVATE_KEY": self.slams_delegation_private_key,
            }
            missing = [
                name
                for name, value in required.items()
                if value is None
                or not (value.get_secret_value() if isinstance(value, SecretStr) else str(value)).strip()
            ]
            if missing:
                raise ValueError(f"SLAMS integration is enabled but required configuration is missing: {', '.join(missing)}")
        if self.redis_enabled and not self.redis_url:
            raise ValueError("REDIS_URL must be configured when REDIS_ENABLED=true")
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

    @property
    def cors_origins(self) -> list[str]:
        """Configured browser origins; credentials are never permitted for wildcards."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return one settings instance per process to avoid repeated environment parsing."""
    return Settings()
