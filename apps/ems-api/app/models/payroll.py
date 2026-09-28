import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PayrollSnapshot(Base):
    __tablename__ = "payroll_snapshots"
    __table_args__ = (UniqueConstraint("employee_id", "payroll_year", "payroll_month", name="uq_payroll_snapshot_employee_month"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    payroll_year: Mapped[int] = mapped_column(Integer, nullable=False)
    payroll_month: Mapped[int] = mapped_column(Integer, nullable=False)
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    finalized_by_admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    working_days: Mapped[int] = mapped_column(Integer, nullable=False)
    present_days: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_leave_days: Mapped[int] = mapped_column(Integer, nullable=False)
    explicit_absent_days: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_attendance_days: Mapped[int] = mapped_column(Integer, nullable=False)
    total_regular_qualifying_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_regular_deficit_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_deficit_recovery_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_unrecovered_deficit_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_raw_overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_paid_overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    late_deduction_days: Mapped[int] = mapped_column(Integer, nullable=False)
    absence_deduction_days: Mapped[int] = mapped_column(Integer, nullable=False)
    total_late_deduction: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_absence_deduction: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_overtime_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    regular_salary_after_absence: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payable_salary: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    compensation_breakdown: Mapped[list] = mapped_column(JSON, nullable=False)
    daily_breakdown: Mapped[list] = mapped_column(JSON, nullable=False)
