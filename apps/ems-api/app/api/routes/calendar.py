from datetime import datetime,date,time,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,or_
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.calendar import CalendarEvent,EventScope
from app.models.holiday import CompanyHoliday
from app.models.employee import Employee,Role
from app.models.leave import LeaveRequest,LeaveStatus
from app.models.audit import AuditEvent,AuditSource,AuditOutcome
from app.schemas.calendar import EventWrite,HolidayWrite
from app.services.holidays import holidays_in_range,is_default_company_holiday
router=APIRouter(prefix='/api/v1/calendar',tags=['calendar'])
def event(e):return {'id':str(e.id),'title':e.title,'description':e.description,'event_type':e.event_type.value,'scope':e.scope.value,'start_at':e.start_at,'end_at':e.end_at,'all_day':e.all_day,'location':e.location,'created_by':str(e.created_by),'kind':'EVENT'}
def owner(e,u):
 if (e.scope == EventScope.PRIVATE and e.created_by!=u.id) or (e.scope == EventScope.COMPANY and u.role != Role.ADMIN): raise HTTPException(403,'Not authorized')
def audit(db,u,op,e):db.add(AuditEvent(actor_employee_id=u.id,operation=op,target_type='CALENDAR_EVENT',target_id=e.id,source=AuditSource.UI,outcome=AuditOutcome.SUCCEEDED,after_state={}))
def holiday(item):return {'id':item['id'],'title':item['name'],'description':None,'event_type':'HOLIDAY','start_at':item['holiday_date'],'end_at':item['holiday_date'],'all_day':True,'location':None,'kind':'HOLIDAY','is_default':item['is_default'],'deletable':item['deletable']}
@router.get('/feed')
def feed(start:date,end:date,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 if end<start:raise HTTPException(422,'Invalid date range')
 a=datetime.combine(start,time.min,tzinfo=timezone.utc);b=datetime.combine(end,time.max,tzinfo=timezone.utc)
 out=[event(x) for x in db.scalars(select(CalendarEvent).where(CalendarEvent.start_at<=b,CalendarEvent.end_at>=a,or_(CalendarEvent.scope==EventScope.COMPANY,CalendarEvent.created_by==user.id)))]
 leaves=db.scalars(select(LeaveRequest).where(LeaveRequest.status==LeaveStatus.APPROVED,LeaveRequest.start_date<=end,LeaveRequest.end_date>=start)).all()
 for l in leaves:
  if l.employee_id==user.id or (user.role == Role.MANAGER and db.get(Employee,l.employee_id).manager_id==user.id): out.append({'id':str(l.id),'title':'Approved leave','event_type':'APPROVED_LEAVE','start_at':l.start_date.isoformat(),'end_at':l.end_date.isoformat(),'all_day':True,'kind':'LEAVE'})
 out.extend(holiday(item) for item in holidays_in_range(db,start,end))
 return out
@router.get('/holidays')
def holidays(start:date,end:date,db:Session=Depends(get_db),_:Employee=Depends(get_current_user)):
 if end<start:raise HTTPException(422,'Invalid date range')
 return holidays_in_range(db,start,end)
@router.post('/holidays')
def create_holiday(body:HolidayWrite,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 if user.role != Role.ADMIN:raise HTTPException(403,'Not authorized')
 if is_default_company_holiday(body.holiday_date):raise HTTPException(422,'Default company holidays are already applied')
 if db.query(CompanyHoliday).filter_by(holiday_date=body.holiday_date).first():raise HTTPException(409,'A company holiday already exists for this date')
 item=CompanyHoliday(holiday_date=body.holiday_date,name=body.name.strip(),created_by=user.id);db.add(item);db.flush();db.add(AuditEvent(actor_employee_id=user.id,operation='create_company_holiday',target_type='COMPANY_HOLIDAY',target_id=item.id,source=AuditSource.UI,outcome=AuditOutcome.SUCCEEDED,after_state={}));db.commit();return {'id':str(item.id),'holiday_date':item.holiday_date.isoformat(),'name':item.name,'is_default':False,'deletable':True}
@router.delete('/holidays/{holiday_id}')
def delete_holiday(holiday_id:str,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 if user.role != Role.ADMIN:raise HTTPException(403,'Not authorized')
 if holiday_id.startswith('default-'):raise HTTPException(422,'Default company holidays cannot be removed')
 try:item=db.get(CompanyHoliday,UUID(holiday_id))
 except ValueError:item=None
 if not item:raise HTTPException(404,'Company holiday not found')
 db.add(AuditEvent(actor_employee_id=user.id,operation='delete_company_holiday',target_type='COMPANY_HOLIDAY',target_id=item.id,source=AuditSource.UI,outcome=AuditOutcome.SUCCEEDED,after_state={}));db.delete(item);db.commit();return {'ok':True}
@router.get('/events/{event_id}')
def get_event(event_id:UUID,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 e=db.get(CalendarEvent,event_id)
 if not e: raise HTTPException(404,'Calendar event not found')
 if e.scope == EventScope.PRIVATE and e.created_by!=user.id:raise HTTPException(404,'Calendar event not found')
 return event(e)
@router.post('/events')
def create(body:EventWrite,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 if body.scope == EventScope.COMPANY and user.role != Role.ADMIN:raise HTTPException(403,'Not authorized')
 e=CalendarEvent(**body.model_dump(),created_by=user.id);db.add(e);db.flush();audit(db,user,'create_calendar_event',e);db.commit();db.refresh(e);return event(e)
@router.patch('/events/{event_id}')
def update(event_id:UUID,body:EventWrite,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 e=db.get(CalendarEvent,event_id)
 if not e:raise HTTPException(404,'Calendar event not found')
 owner(e,user)
 if body.scope == EventScope.COMPANY and user.role != Role.ADMIN:raise HTTPException(403,'Not authorized')
 for k,v in body.model_dump().items():setattr(e,k,v)
 audit(db,user,'update_calendar_event',e);db.commit();return event(e)
@router.delete('/events/{event_id}')
def delete(event_id:UUID,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 e=db.get(CalendarEvent,event_id)
 if not e:raise HTTPException(404,'Calendar event not found')
 owner(e,user);audit(db,user,'delete_calendar_event',e);db.delete(e);db.commit();return {'ok':True}
