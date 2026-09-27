from datetime import datetime, time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord, AttendanceSource, AttendanceStatus, OvertimeSession
from app.models.employee import Employee, Role
from app.models.notification import NotificationCategory, Notification
from app.services.holidays import is_working_day
from app.services.notifications import create_notification

WORKDAY_END = time(17, 0)

def now(): return datetime.now().astimezone()
def subject(user):
    if user.role == Role.ADMIN: raise HTTPException(403, "Administrators cannot use attendance workflows")
    return user
def regular_minutes(record):
    if not record.regular_check_in_at or not record.regular_check_out_at: return None
    end = min(record.regular_check_out_at, record.regular_check_out_at.replace(hour=17, minute=0, second=0, microsecond=0))
    return max(0, int((end-record.regular_check_in_at).total_seconds()//60))
def check_in(db:Session,user:Employee,clock=now):
    user=subject(user); moment=clock(); day=moment.date()
    if not is_working_day(db,day): raise HTTPException(409,'Attendance is unavailable on a non-working day')
    record=db.query(AttendanceRecord).filter_by(employee_id=user.id,attendance_date=day).first()
    if record and record.status != AttendanceStatus.PRESENT: raise HTTPException(409,'Existing leave or absence cannot be overwritten')
    if record and record.regular_check_in_at: raise HTTPException(409,'Already checked in')
    if not record: record=AttendanceRecord(employee_id=user.id,attendance_date=day,status=AttendanceStatus.PRESENT,source=AttendanceSource.FACE);db.add(record)
    record.regular_check_in_at=moment; db.commit(); db.refresh(record); return record
def check_out(db:Session,user:Employee,clock=now):
    user=subject(user); moment=clock(); record=db.query(AttendanceRecord).filter_by(employee_id=user.id,attendance_date=moment.date()).first()
    if not record or not record.regular_check_in_at: raise HTTPException(409,'Check in is required before check out')
    if record.regular_check_out_at: raise HTTPException(409,'Already checked out')
    if moment <= record.regular_check_in_at: raise HTTPException(422,'Check out must be after check in')
    record.regular_check_out_at=moment; db.commit(); db.refresh(record); return record
def ot_in(db:Session,user:Employee,clock=now):
    user=subject(user); moment=clock(); day=moment.date()
    if moment.time() < WORKDAY_END: raise HTTPException(409,'Overtime can start at 17:00 or later')
    if not is_working_day(db,day): raise HTTPException(409,'Overtime is unavailable on a non-working day')
    record=db.query(AttendanceRecord).filter_by(employee_id=user.id,attendance_date=day).first()
    if not record or not record.regular_check_in_at: raise HTTPException(409,'Regular check in is required before overtime')
    if db.query(OvertimeSession).filter_by(employee_id=user.id,check_out_at=None).first(): raise HTTPException(409,'An overtime session is already open')
    session=OvertimeSession(employee_id=user.id,attendance_date=day,check_in_at=moment);db.add(session);db.commit();db.refresh(session);return session
def ot_out(db:Session,user:Employee,clock=now):
    user=subject(user); moment=clock(); session=db.query(OvertimeSession).filter_by(employee_id=user.id,check_out_at=None).first()
    if not session: raise HTTPException(409,'No open overtime session')
    if moment <= session.check_in_at: raise HTTPException(422,'Overtime check out must be after check in')
    session.check_out_at=moment;db.commit();db.refresh(session);return session
def continuation_notifications(db:Session,clock=now):
    moment=clock();
    if moment.time()<WORKDAY_END or not is_working_day(db,moment.date()): return 0
    rows=db.query(AttendanceRecord).filter_by(attendance_date=moment.date(),status=AttendanceStatus.PRESENT,regular_check_out_at=None).all(); created=0
    for row in rows:
        employee=db.get(Employee,row.employee_id)
        if employee.role==Role.ADMIN or db.query(Notification).filter_by(recipient_id=employee.id,related_entity_type='ATTENDANCE_CONTINUATION',related_entity_id=row.id).first(): continue
        create_notification(db,recipient_id=employee.id,category=NotificationCategory.SYSTEM,title='Regular workday ended',message='Your regular workday has ended. If you are continuing work, start an overtime session.',related_entity_type='ATTENDANCE_CONTINUATION',related_entity_id=row.id);created+=1
    db.commit();return created
