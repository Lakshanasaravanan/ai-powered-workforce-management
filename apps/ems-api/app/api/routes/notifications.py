from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.employee import Employee
from app.models.notification import Notification
from app.schemas.notifications import (
    NotificationResponse,
    ReadAllResponse,
    UnreadCountResponse,
)


router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def get_recipient_notification_or_404(
    db: Session, notification_id: str, recipient_id: UUID
) -> Notification:
    try:
        notification = db.get(Notification, UUID(notification_id))
    except ValueError:
        notification = None
    if notification is None or notification.recipient_id != recipient_id:
        raise HTTPException(404, "Notification not found")
    return notification


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    user: Employee = Depends(get_current_user), db: Session = Depends(get_db)
) -> UnreadCountResponse:
    count = (
        db.query(func.count(Notification.id))
        .filter(Notification.recipient_id == user.id, Notification.is_read.is_(False))
        .scalar()
    )
    return UnreadCountResponse(unread_count=count)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: str,
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Notification:
    notification = get_recipient_notification_or_404(db, notification_id, user.id)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(notification)
    return notification


@router.post("/read-all", response_model=ReadAllResponse)
def mark_all_read(
    user: Employee = Depends(get_current_user), db: Session = Depends(get_db)
) -> ReadAllResponse:
    result = db.execute(
        update(Notification)
        .where(Notification.recipient_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(timezone.utc).replace(tzinfo=None))
    )
    db.commit()
    return ReadAllResponse(updated_count=result.rowcount)
