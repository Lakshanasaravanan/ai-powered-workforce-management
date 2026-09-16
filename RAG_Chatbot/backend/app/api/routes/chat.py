from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from app.agents.models import ExecutionContext
from app.api.dependencies import AgentServiceDependency, CurrentUser
from app.core.logging import request_id_context
from app.schemas.agent import AgentResponse, ConfirmationRequest
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/api/v1", tags=["chat"])


def _context(current_user, conversation_id: UUID) -> ExecutionContext:
    return ExecutionContext(
        employee_id=current_user.employee_id,
        display_name=current_user.display_name,
        roles=frozenset(current_user.roles),
        request_id=request_id_context.get(),
        conversation_id=conversation_id,
        auth_subject=current_user.employee_id,
    )

def _limit(request: Request, employee_id: str, category: str) -> None:
    from app.core.config import get_settings
    from app.services.rate_limit import RateLimitExceeded
    settings=get_settings(); limit=settings.chat_rate_limit_per_minute if category == "chat" else settings.confirmation_rate_limit_per_minute
    try: retry=request.app.state.rate_limiter.check(f"{category}:{employee_id}", limit)
    except RateLimitExceeded:
        import logging
        logging.getLogger("agentic_rag.rate_limit").warning("rate_limit_exceeded", extra={"employee_id": employee_id, "status": "limited"})
        raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": "60"})


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request, current_user: CurrentUser, agent_service: AgentServiceDependency) -> AgentResponse:
    """Authenticated employee assistance through the controlled agent tool boundary."""
    _limit(request, current_user.employee_id, "chat"); conversation_id = payload.conversation_id or uuid4()
    return agent_service.respond(payload.message, _context(current_user, conversation_id))


@router.post("/chat/confirm", response_model=AgentResponse)
def confirm_chat_action(payload: ConfirmationRequest, request: Request, current_user: CurrentUser, agent_service: AgentServiceDependency) -> AgentResponse:
    _limit(request, current_user.employee_id, "confirmation")
    return agent_service.confirm(payload, _context(current_user, payload.conversation_id))
