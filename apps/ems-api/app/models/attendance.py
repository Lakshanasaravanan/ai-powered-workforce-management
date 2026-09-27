import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    LEAVE = "LEAVE"
    ABSENT = "ABSENT"


class AttendanceSource(str, Enum):
    FACE = "FACE"
    APPROVED_LEAVE = "APPROVED_LEAVE"
    ADMIN_OVERRIDE = "ADMIN_OVERRIDE"


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_employee_date"),
        Index("ix_attendance_employee_date", "employee_id", "attendance_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), nullable=False)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(SAEnum(AttendanceStatus), nullable=False)
    regular_check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    regular_check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    leave_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leave_requests.id"), nullable=True)
    leave_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[AttendanceSource] = mapped_column(SAEnum(AttendanceSource), nullable=False)
    admin_modified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    admin_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_modification_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
