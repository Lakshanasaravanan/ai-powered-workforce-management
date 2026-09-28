import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AuditSource(str, Enum):
    UI = "UI"
    AI_AGENT = "AI_AGENT"


class AuditOutcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source: Mapped[AuditSource] = mapped_column(SAEnum(AuditSource), nullable=False)
    outcome: Mapped[AuditOutcome] = mapped_column(SAEnum(AuditOutcome), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
