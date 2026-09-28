from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.employee import Employee
from app.models.audit import AuditEvent, AuditOutcome, AuditSource
from app.models.payroll import PayrollSnapshot
from app.schemas.payroll import PayrollPreview, PayrollSnapshotRead
from app.services.payroll import _json_value, month_bounds, payroll_preview, snapshot_dict


router = APIRouter(prefix="/api/v1/payroll", tags=["payroll"])


@router.get("/{employee_id}", response_model=PayrollPreview)
def preview(
    employee_id: str,
    year: int = Query(..., ge=2000, le=9999),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    _: Employee = Depends(require_admin),
):
    from app.api.routes.employees import employee_or_404
    return payroll_preview(db, employee_or_404(db, employee_id), year, month)


@router.post("/{employee_id}/finalize", response_model=PayrollSnapshotRead)
def finalize(
    employee_id: str, year: int = Query(..., ge=2000, le=9999), month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db), admin: Employee = Depends(require_admin),
):
    from app.api.routes.employees import employee_or_404
    if month_bounds(year, month)[1] >= date.today().replace(day=1):
        raise HTTPException(422, "Only completed past payroll months may be finalized")
    employee = employee_or_404(db, employee_id)
    if db.query(PayrollSnapshot).filter_by(employee_id=employee.id, payroll_year=year, payroll_month=month).first():
        raise HTTPException(409, "Payroll is already finalized for this month")
    calculation = payroll_preview(db, employee, year, month)
    if calculation["missing_attendance_days"]:
        raise HTTPException(422, "Payroll cannot be finalized while attendance is missing")
    if calculation["open_overtime_sessions"]:
        raise HTTPException(422, "Payroll cannot be finalized while overtime is open")
    snapshot = PayrollSnapshot(
        employee_id=employee.id, payroll_year=year, payroll_month=month, finalized_by_admin_id=admin.id,
        working_days=calculation["working_days"], present_days=calculation["present_days"], paid_leave_days=calculation["paid_leave_days"], explicit_absent_days=calculation["explicit_absent_days"], missing_attendance_days=calculation["missing_attendance_days"], total_regular_qualifying_minutes=calculation["total_regular_qualifying_minutes"], total_regular_deficit_minutes=calculation["total_regular_deficit_minutes"], total_deficit_recovery_minutes=calculation["total_deficit_recovery_minutes"], total_unrecovered_deficit_minutes=calculation["total_unrecovered_deficit_minutes"], total_raw_overtime_minutes=calculation["total_raw_overtime_minutes"], total_paid_overtime_minutes=calculation["total_paid_overtime_minutes"], late_deduction_days=calculation["late_deduction_days"], absence_deduction_days=calculation["absence_deduction_days"], total_late_deduction=calculation["total_late_deduction"], total_absence_deduction=calculation["total_absence_deduction"], total_overtime_pay=calculation["total_overtime_pay"], regular_salary_after_absence=calculation["regular_salary_after_absence"], payable_salary=calculation["payable_salary_preview"], compensation_breakdown=_json_value(calculation["compensation_periods"]), daily_breakdown=_json_value(calculation["daily_breakdown"]),
    )
    try:
        db.add(snapshot); db.flush()
        db.add(AuditEvent(actor_employee_id=admin.id, operation="finalize_payroll", target_type="PAYROLL_SNAPSHOT", target_id=snapshot.id, source=AuditSource.UI, outcome=AuditOutcome.SUCCEEDED, after_state={"employee_id": str(employee.id), "year": year, "month": month, "snapshot_id": str(snapshot.id), "payable_salary": format(calculation["payable_salary_preview"], ".2f")}))
        db.commit(); db.refresh(snapshot)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Payroll is already finalized for this month")
    return snapshot_dict(snapshot)


@router.get("/{employee_id}/finalized", response_model=PayrollSnapshotRead)
def finalized(employee_id: str, year: int = Query(..., ge=2000, le=9999), month: int = Query(..., ge=1, le=12), db: Session = Depends(get_db), _: Employee = Depends(require_admin)):
    from app.api.routes.employees import employee_or_404
    employee = employee_or_404(db, employee_id)
    item = db.query(PayrollSnapshot).filter_by(employee_id=employee.id, payroll_year=year, payroll_month=month).first()
    if not item: raise HTTPException(404, "Finalized payroll not found")
    return snapshot_dict(item)


@router.get("/{employee_id}/finalized-history", response_model=list[PayrollSnapshotRead])
def finalized_history(employee_id: str, db: Session = Depends(get_db), _: Employee = Depends(require_admin)):
    from app.api.routes.employees import employee_or_404
    employee = employee_or_404(db, employee_id)
    return [snapshot_dict(item) for item in db.query(PayrollSnapshot).filter_by(employee_id=employee.id).order_by(PayrollSnapshot.payroll_year.desc(), PayrollSnapshot.payroll_month.desc())]
