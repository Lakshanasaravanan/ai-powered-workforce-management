from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord, AttendanceSource, AttendanceStatus
from app.models.leave import LeaveRequest
from app.services.holidays import is_working_day


def project_approved_leave(db: Session, request: LeaveRequest) -> None:
    day = request.start_date
    while day <= request.end_date:
        if is_working_day(db, day):
            existing = db.query(AttendanceRecord).filter_by(employee_id=request.employee_id, attendance_date=day).one_or_none()
            if existing is None:
                db.add(AttendanceRecord(employee_id=request.employee_id, attendance_date=day, status=AttendanceStatus.LEAVE, source=AttendanceSource.APPROVED_LEAVE, leave_request_id=request.id, leave_type=request.leave_type.value))
            elif not (existing.status == AttendanceStatus.LEAVE and existing.source == AttendanceSource.APPROVED_LEAVE and existing.leave_request_id == request.id):
                raise HTTPException(409, "Approved leave conflicts with existing attendance")
        day += timedelta(days=1)
