from uuid import uuid4

from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.api.dependencies import RAGServiceDependency
from app.rag.service import RAGService, RAGServiceError
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user: CurrentUser, rag_service: RAGServiceDependency) -> ChatResponse:
    """Authenticated company-policy Q&A; identity is intentionally not used by Phase 2 RAG."""
    conversation_id = payload.conversation_id or uuid4()
    try:
        result = rag_service.answer(payload.message)
    except RAGServiceError:
        # The centralized handler deliberately hides provider/vector implementation details.
        raise
    return ChatResponse(answer=result.answer, sources=result.sources, conversation_id=conversation_id)
