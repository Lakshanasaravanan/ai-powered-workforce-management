from datetime import date, datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.attendance import AttendanceRecord
from app.models.employee import Employee, Role
from app.services.holidays import holidays_in_range


router = APIRouter(prefix="/api/v1/attendance", tags=["attendance"])
WORKDAY_START = time(9, 0)


def _subject_or_422(db: Session, employee_id: UUID) -> Employee:
    employee = db.get(Employee, employee_id)
    if not employee or not employee.is_active or employee.role == Role.ADMIN:
        raise HTTPException(422, "Attendance is available only for active employees and managers")
    return employee


def _authorize_target(db: Session, viewer: Employee, employee_id: UUID) -> Employee:
    subject = _subject_or_422(db, employee_id)
    if viewer.role == Role.ADMIN:
        return subject
    if viewer.id == subject.id:
        return subject
    if viewer.role == Role.MANAGER and subject.manager_id == viewer.id:
        return subject
    raise HTTPException(403, "Not authorized to view this attendance")


def _record_payload(record: AttendanceRecord) -> dict:
    check_in = record.regular_check_in_at
    check_out = record.regular_check_out_at
    late_minutes = None
    if check_in:
        arrived = check_in.time().replace(tzinfo=None)
        late_minutes = max(0, int((datetime.combine(record.attendance_date, arrived) - datetime.combine(record.attendance_date, WORKDAY_START)).total_seconds() // 60))
    worked_minutes = None
    if check_in and check_out:
        worked_minutes = max(0, int((check_out - check_in).total_seconds() // 60))
    return {
        "id": str(record.id),
        "attendance_date": record.attendance_date.isoformat(),
        "status": record.status.value,
        "source": record.source.value,
        "regular_check_in_at": check_in.isoformat() if check_in else None,
        "regular_check_out_at": check_out.isoformat() if check_out else None,
        "leave_request_id": str(record.leave_request_id) if record.leave_request_id else None,
        "leave_type": record.leave_type,
        "late_minutes": late_minutes,
        "worked_minutes": worked_minutes,
    }


def _feed(db: Session, employee: Employee, start: date, end: date) -> dict:
    if end < start:
        raise HTTPException(422, "Invalid date range")
    records = db.scalars(select(AttendanceRecord).where(AttendanceRecord.employee_id == employee.id, AttendanceRecord.attendance_date >= start, AttendanceRecord.attendance_date <= end).order_by(AttendanceRecord.attendance_date)).all()
    return {
        "employee": {"id": str(employee.id), "employee_code": employee.employee_code, "full_name": employee.full_name, "role": employee.role.value},
        "records": [_record_payload(record) for record in records],
        "holidays": [{"date": item["holiday_date"], "name": item["name"]} for item in holidays_in_range(db, start, end)],
    }


@router.get("/me")
def own_attendance(start: date, end: date, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if user.role == Role.ADMIN:
        raise HTTPException(403, "Administrators do not have attendance records")
    return _feed(db, _subject_or_422(db, user.id), start, end)


@router.get("/employees/{employee_id}")
def employee_attendance(employee_id: UUID, start: date, end: date, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    return _feed(db, _authorize_target(db, user, employee_id), start, end)
