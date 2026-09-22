from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    app_name: str = "InfoTech Workspace EMS API"
    environment: str = "development"
    api_version: str = "v1"
    database_url: str = "postgresql+asyncpg://infotech:infotech-local-only@localhost:5432/infotech"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = 60
    websocket_ticket_ttl_seconds: int = Field(default=60, ge=15, le=300)
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("jwt_secret")
    @classmethod
    def require_hs256_strength(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(value.encode("utf-8")) < 32 or "replace-with" in normalized or "change-me" in normalized:
            raise ValueError("JWT_SECRET must be a non-placeholder value of at least 32 bytes for HS256")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]
