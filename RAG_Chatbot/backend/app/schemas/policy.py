"""Strict public contract for the InfoTech policy-QA API."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.rag import SourceCitation


class PolicyQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=6000)
    conversation_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def require_non_whitespace_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class PolicyQueryResponse(BaseModel):
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)
    conversation_id: UUID
    request_id: str | None = None
