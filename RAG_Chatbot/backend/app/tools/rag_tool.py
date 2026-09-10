"""Thin tool wrapper that preserves the existing RAG service boundary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.agents.models import ExecutionContext
from app.rag.service import RAGService
from app.schemas.agent import ToolCategory, ToolPermission
from app.schemas.rag import SourceCitation
from app.tools.base import Tool, ToolSpec


class PolicyAnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=6000)


class PolicyAnswerResult(BaseModel):
    answer: str
    sources: list[SourceCitation]


class PolicyAnswerTool(Tool):
    spec = ToolSpec(name="policy_answer", description="Answer a company-policy question with grounded RAG evidence.", category=ToolCategory.KNOWLEDGE, permission=ToolPermission.KNOWLEDGE)
    input_model = PolicyAnswerInput

    def __init__(self, rag_service: RAGService) -> None:
        self.rag_service = rag_service

    def execute(self, context: ExecutionContext, tool_input: PolicyAnswerInput) -> PolicyAnswerResult:
        answer = self.rag_service.answer(tool_input.question)
        return PolicyAnswerResult(answer=answer.answer, sources=answer.sources)
