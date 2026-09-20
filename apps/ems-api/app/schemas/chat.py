from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class DirectConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_employee_id: UUID
class GroupConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    participant_employee_ids: list[UUID] = Field(min_length=1, max_length=50)
class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
