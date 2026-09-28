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


class PayrollDay(BaseModel):
    date: str
    classification: str
    regular_qualifying_minutes: int
    arrival_delay_minutes: int
    regular_deficit_minutes: int
    raw_overtime_minutes: int
    deficit_recovery_minutes: int
    unrecovered_deficit_minutes: int
    paid_overtime_minutes: int
    late_deduction_applied: bool
    late_deduction_amount: Decimal
    absence_deduction: Decimal
    overtime_pay: Decimal


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
    total_regular_qualifying_minutes: int
    total_regular_deficit_minutes: int
    total_deficit_recovery_minutes: int
    total_unrecovered_deficit_minutes: int
    total_raw_overtime_minutes: int
    total_paid_overtime_minutes: int
    late_deduction_days: int
    total_late_deduction: Decimal
    absence_deduction_days: int
    total_absence_deduction: Decimal
    total_overtime_pay: Decimal
    regular_salary_after_absence: Decimal
    payable_salary_preview: Decimal
    daily_breakdown: list[PayrollDay]


class PayrollSnapshotRead(BaseModel):
    id: str
    employee_id: str
    payroll_year: int
    payroll_month: int
    finalized_at: str
    finalized_by_admin_id: str
    working_days: int
    present_days: int
    paid_leave_days: int
    explicit_absent_days: int
    missing_attendance_days: int
    total_regular_qualifying_minutes: int
    total_regular_deficit_minutes: int
    total_deficit_recovery_minutes: int
    total_unrecovered_deficit_minutes: int
    total_raw_overtime_minutes: int
    total_paid_overtime_minutes: int
    late_deduction_days: int
    absence_deduction_days: int
    total_late_deduction: Decimal
    total_absence_deduction: Decimal
    total_overtime_pay: Decimal
    regular_salary_after_absence: Decimal
    payable_salary: Decimal
    compensation_breakdown: list[dict]
    daily_breakdown: list[dict]
