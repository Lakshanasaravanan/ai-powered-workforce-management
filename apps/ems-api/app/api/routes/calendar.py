from datetime import datetime,date,time,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.calendar import CalendarEvent
from app.models.employee import Employee,Role
from app.models.leave import LeaveRequest,LeaveStatus
from app.models.audit import AuditEvent,AuditSource,AuditOutcome
from app.schemas.calendar import EventWrite
router=APIRouter(prefix='/api/v1/calendar',tags=['calendar'])
def event(e):return {'id':str(e.id),'title':e.title,'description':e.description,'event_type':e.event_type.value,'start_at':e.start_at,'end_at':e.end_at,'all_day':e.all_day,'location':e.location,'created_by':str(e.created_by),'kind':'EVENT'}
def owner(e,u):
 if e.created_by!=u.id and u.role is not Role.ADMIN: raise HTTPException(403,'Not authorized')
def audit(db,u,op,e):db.add(AuditEvent(actor_employee_id=u.id,operation=op,target_type='CALENDAR_EVENT',target_id=e.id,source=AuditSource.UI,outcome=AuditOutcome.SUCCEEDED,after_state={}))
@router.get('/feed')
def feed(start:date,end:date,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 if end<start:raise HTTPException(422,'Invalid date range')
 a=datetime.combine(start,time.min,tzinfo=timezone.utc);b=datetime.combine(end,time.max,tzinfo=timezone.utc)
 out=[event(x) for x in db.scalars(select(CalendarEvent).where(CalendarEvent.start_at<=b,CalendarEvent.end_at>=a))]
 leaves=db.scalars(select(LeaveRequest).where(LeaveRequest.status==LeaveStatus.APPROVED,LeaveRequest.start_date<=end,LeaveRequest.end_date>=start)).all()
 for l in leaves:
  if l.employee_id==user.id or (user.role is Role.MANAGER and db.get(Employee,l.employee_id).manager_id==user.id): out.append({'id':str(l.id),'title':'Approved leave','event_type':'APPROVED_LEAVE','start_at':l.start_date.isoformat(),'end_at':l.end_date.isoformat(),'all_day':True,'kind':'LEAVE'})
 return out
@router.get('/events/{event_id}')
def get_event(event_id:UUID,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 e=db.get(CalendarEvent,event_id)
 if not e: raise HTTPException(404,'Calendar event not found')
 # Persisted calendar events are company events; private leave never has an event record.
 return event(e)
@router.post('/events')
def create(body:EventWrite,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 if user.role not in (Role.ADMIN,Role.MANAGER):raise HTTPException(403,'Not authorized')
 e=CalendarEvent(**body.model_dump(),created_by=user.id);db.add(e);db.flush();audit(db,user,'create_calendar_event',e);db.commit();db.refresh(e);return event(e)
@router.patch('/events/{event_id}')
def update(event_id:UUID,body:EventWrite,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 e=db.get(CalendarEvent,event_id)
 if not e:raise HTTPException(404,'Calendar event not found')
 owner(e,user)
 for k,v in body.model_dump().items():setattr(e,k,v)
 audit(db,user,'update_calendar_event',e);db.commit();return event(e)
@router.delete('/events/{event_id}')
def delete(event_id:UUID,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
 e=db.get(CalendarEvent,event_id)
 if not e:raise HTTPException(404,'Calendar event not found')
 owner(e,user);audit(db,user,'delete_calendar_event',e);db.delete(e);db.commit();return {'ok':True}
