from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    conversation_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def require_non_whitespace_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class ChatResponse(BaseModel):
    answer: str
    conversation_id: UUID
