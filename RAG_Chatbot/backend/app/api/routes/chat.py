from uuid import uuid4

from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user: CurrentUser) -> ChatResponse:
    """Authenticated Phase 1 placeholder; RAG and agent behavior arrive in later phases."""
    conversation_id = payload.conversation_id or uuid4()
    return ChatResponse(
        answer="The Agentic RAG assistant foundation is ready. RAG capabilities will be added in a later phase.",
        conversation_id=conversation_id,
    )
