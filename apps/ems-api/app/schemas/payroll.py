from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class CompensationPeriod(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    effective_from: str
    effective_to: str
    working_days: int
    monthly_salary: Decimal
    derived_daily_rate: Decimal
    prorated_salary_foundation: Decimal
    overtime_hourly_rate: Decimal
    late_deduction_amount: Decimal


class PayrollPreview(BaseModel):
    employee_id: str
    employee_code: str
    employee_name: str
    year: int
    month: int
    working_days: int
    present_days: int
    paid_leave_days: int
    explicit_absent_days: int
    missing_attendance_days: int
    regular_worked_minutes: int
    regular_records_without_completed_checkout: int
    raw_overtime_minutes: int
    open_overtime_sessions: int
    monthly_salary: Decimal
    derived_daily_rate: Decimal
    overtime_hourly_rate: Decimal
    late_deduction_amount: Decimal
    compensation_periods: list[CompensationPeriod]
