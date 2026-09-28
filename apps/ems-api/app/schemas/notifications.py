from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationCategory


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: NotificationCategory
    title: str
    message: str
    is_read: bool
    read_at: datetime | None
    related_entity_type: str | None
    related_entity_id: UUID | None
    created_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int


class ReadAllResponse(BaseModel):
    updated_count: int
