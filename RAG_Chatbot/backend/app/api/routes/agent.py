"""InfoTech policy-QA endpoint, intentionally isolated from legacy tools."""

from __future__ import annotations

import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status

from app.agents.models import PolicyExecutionContext
from app.api.dependencies import InfoTechIdentity, RAGServiceDependency
from app.core.logging import request_id_context
from app.schemas.policy import PolicyQueryRequest, PolicyQueryResponse


router = APIRouter(prefix="/api/v1/agent", tags=["infotech-policy-agent"])
_ACTION_REQUEST = re.compile(r"\b(apply|request|submit|regulari[sz]e|cancel)\b.*\b(leave|attendance)\b", re.IGNORECASE)


@router.post("/query", response_model=PolicyQueryResponse)
def query_policy(
    payload: PolicyQueryRequest,
    request: Request,
    identity: InfoTechIdentity,
    rag_service: RAGServiceDependency,
) -> PolicyQueryResponse:
    """Answer policy questions only; no planner, workforce provider, or action tool is reachable."""
    index = request.app.state.rag_index_status
    if not index.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy knowledge is unavailable; an operator must run the offline index build.",
        )
    context = PolicyExecutionContext(
        employee_id=identity.employee_id,
        employee_code=identity.employee_code,
        display_name=identity.display_name,
        role=identity.role,
        request_id=request_id_context.get(),
        conversation_id=payload.conversation_id or uuid4(),
    )
    if _ACTION_REQUEST.search(payload.message):
        answer = "This assistant currently supports company-policy questions and cannot perform workforce actions."
        sources = []
    else:
        result = rag_service.answer(payload.message)
        answer, sources = result.answer, result.sources
    return PolicyQueryResponse(
        answer=answer,
        sources=sources,
        conversation_id=context.conversation_id,
        request_id=context.request_id,
    )
