"""Safe Phase 5 action lifecycle request and response contracts."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.services.infotech_pending_actions import InfoTechActionState

class ActionConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: UUID

class ActionStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    state: InfoTechActionState
    message: str
    conversation_id: UUID
    request_id: str | None = None
