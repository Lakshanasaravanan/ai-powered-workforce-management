from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationCategory


def create_notification(
    db: Session,
    *,
    recipient_id: UUID,
    category: NotificationCategory,
    title: str,
    message: str,
    related_entity_type: str | None = None,
    related_entity_id: UUID | None = None,
) -> Notification:
    notification = Notification(
        recipient_id=recipient_id,
        category=category,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    db.add(notification)
    return notification
