from uuid import UUID, uuid4

from fastapi import APIRouter

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


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user: CurrentUser, agent_service: AgentServiceDependency) -> AgentResponse:
    """Authenticated employee assistance through the controlled agent tool boundary."""
    conversation_id = payload.conversation_id or uuid4()
    return agent_service.respond(payload.message, _context(current_user, conversation_id))


@router.post("/chat/confirm", response_model=AgentResponse)
def confirm_chat_action(payload: ConfirmationRequest, current_user: CurrentUser, agent_service: AgentServiceDependency) -> AgentResponse:
    return agent_service.confirm(payload, _context(current_user, payload.conversation_id))
