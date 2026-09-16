import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LeaveType(str, Enum):
    CASUAL = "CASUAL"
    MEDICAL = "MEDICAL"
    EMERGENCY = "EMERGENCY"
    DAY_OFF = "DAY_OFF"


class LeaveStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LeaveDuration(str, Enum):
    FULL_DAY = "FULL_DAY"
    HALF_DAY = "HALF_DAY"


class HalfDayPeriod(str, Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"


class DecisionSource(str, Enum):
    AUTOMATIC_POLICY = "AUTOMATIC_POLICY"
    MANAGER = "MANAGER"


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    leave_type: Mapped[LeaveType] = mapped_column(SAEnum(LeaveType), nullable=False)
    status: Mapped[LeaveStatus] = mapped_column(SAEnum(LeaveStatus), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    duration: Mapped[LeaveDuration] = mapped_column(SAEnum(LeaveDuration), nullable=False)
    half_day_period: Mapped[HalfDayPeriod | None] = mapped_column(
        SAEnum(HalfDayPeriod), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decision_source: Mapped[DecisionSource | None] = mapped_column(
        SAEnum(DecisionSource), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
