"""Typed tool contract. Tools receive only server-built execution context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.agents.models import ExecutionContext
from app.schemas.agent import ToolCategory, ToolPermission


class ToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=80)
    description: str
    category: ToolCategory
    permission: ToolPermission
    requires_confirmation: bool = False


class Tool(ABC):
    spec: ClassVar[ToolSpec]
    input_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def execute(self, context: ExecutionContext, tool_input: BaseModel) -> BaseModel: ...
