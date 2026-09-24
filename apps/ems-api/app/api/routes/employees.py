from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_,func
from uuid import UUID
from app.db.session import get_db
from app.models.employee import Employee,Role,CompensationConfiguration
from app.core.security import hash_password
from app.api.dependencies import get_current_user,require_admin,require_manager
from app.api.routes.auth import summary
router=APIRouter(prefix='/api/v1/employees')
def canonical_email(value):
 email=str(value or '').strip().lower()
 if email.count('@')!=1:raise HTTPException(422,'Invalid company email')
 return email
def employee_or_404(db,employee_id):
 try:u=db.get(Employee,UUID(employee_id))
 except ValueError:u=None
 if not u:raise HTTPException(404,'Employee not found')
 return u
def audit(db,user,operation,target):
 from app.models.audit import AuditEvent,AuditOutcome,AuditSource
 db.add(AuditEvent(actor_employee_id=user.id,operation=operation,target_type='EMPLOYEE',target_id=target.id,source=AuditSource.UI,outcome=AuditOutcome.SUCCEEDED,after_state={}))
def validate_manager(db,manager_id,self_id=None):
 if not manager_id:return None
 try:manager=db.get(Employee,UUID(str(manager_id)))
 except ValueError:raise HTTPException(422,'Invalid manager_id')
 if not manager:raise HTTPException(422,'Invalid manager_id')
 if self_id and str(manager.id)==str(self_id):raise HTTPException(422,'Employee cannot manage themselves')
 if self_id:
  seen=set();cursor=manager
  while cursor:
   if str(cursor.id)==str(self_id):raise HTTPException(422,'Manager assignment would create a reporting cycle')
   if cursor.id in seen:raise HTTPException(422,'Existing reporting hierarchy contains a cycle')
   seen.add(cursor.id);cursor=db.get(Employee,cursor.manager_id) if cursor.manager_id else None
 return manager.id
@router.post('')
def create(body:dict,db:Session=Depends(get_db),_:Employee=Depends(require_admin)):
 code=str(body.get('employee_code','')).strip().upper();role=Role(body['role']);email=canonical_email(body.get('company_email'))
 if role in (Role.EMPLOYEE,Role.MANAGER):
  if email!=f'{code.lower()}@infotech.local':raise HTTPException(422,'Employee and Manager email must match employee_code@infotech.local')
  email=f'{code}@infotech.local'
 if db.query(Employee).filter(or_(func.lower(Employee.company_email)==email,Employee.employee_code==code)).first():raise HTTPException(409,'Duplicate employee code or company email')
 temp=body.get('temporary_password','welcome-change-me')
 u=Employee(employee_code=code,full_name=body['full_name'],company_email=email,role=role,designation=body['designation'],department=body['department'],manager_id=validate_manager(db,body.get('manager_id')),password_hash=hash_password('disabled'),temporary_password_hash=hash_password(temp))
 db.add(u);db.commit();db.refresh(u);return {**summary(u),'temporary_password':temp}
@router.get('')
def list_(db:Session=Depends(get_db),_:Employee=Depends(require_admin)):return [summary(x) for x in db.query(Employee).all()]
@router.get('/search')
def search(q:str,db:Session=Depends(get_db),_:Employee=Depends(get_current_user)):
 term=f'%{q}%';return [summary(x) for x in db.query(Employee).filter(Employee.is_active,or_(Employee.full_name.ilike(term),Employee.company_email.ilike(term),Employee.employee_code.ilike(term))).all()]
@router.get('/me/direct-reports')
def reports(user:Employee=Depends(require_manager),db:Session=Depends(get_db)):return [summary(x) for x in db.query(Employee).filter_by(manager_id=user.id,is_active=True).all()]
@router.get('/me/manager')
def manager(user:Employee=Depends(get_current_user),db:Session=Depends(get_db)):
 return {'manager':summary(db.get(Employee,user.manager_id)) if user.manager_id and db.get(Employee,user.manager_id) else None}
@router.get('/{employee_id}')
def one(employee_id:str,db:Session=Depends(get_db),_:Employee=Depends(require_admin)):
 try:u=db.get(Employee,UUID(employee_id))
 except ValueError:u=None
 if not u:raise HTTPException(404,'Employee not found')
 return summary(u)
@router.patch('/{employee_id}')
def edit(employee_id:str,body:dict,db:Session=Depends(get_db),_:Employee=Depends(require_admin)):
 try:u=db.get(Employee,UUID(employee_id))
 except ValueError:u=None
 if not u:raise HTTPException(404,'Employee not found')
 for key in ('full_name','designation','department','is_active'):
  if key in body:setattr(u,key,body[key])
 if 'role' in body:u.role=Role(body['role'])
 if body.get('is_active') is True:u.archived_at=None
 if 'manager_id' in body:u.manager_id=validate_manager(db,body['manager_id'],u.id)
 db.commit();return summary(u)

@router.delete('/{employee_id}')
def archive(employee_id:str,db:Session=Depends(get_db),user:Employee=Depends(require_admin)):
 u=employee_or_404(db,employee_id)
 if u.id==user.id:raise HTTPException(422,'An administrator cannot archive their own account')
 if db.query(Employee).filter(Employee.manager_id==u.id,Employee.is_active.is_(True)).first():raise HTTPException(422,'Reassign active direct reports before archiving this manager')
 u.is_active=False;u.archived_at=datetime.utcnow();audit(db,user,'archive_employee',u);db.commit();return {'ok':True}

@router.get('/{employee_id}/compensation')
def compensation_history(employee_id:str,db:Session=Depends(get_db),_:Employee=Depends(require_admin)):
 u=employee_or_404(db,employee_id);items=db.query(CompensationConfiguration).filter_by(employee_id=u.id).order_by(CompensationConfiguration.effective_from.desc()).all()
 return [{'id':str(x.id),'monthly_salary':str(x.monthly_salary),'overtime_hourly_rate':str(x.overtime_hourly_rate),'late_deduction_amount':str(x.late_deduction_amount),'effective_from':x.effective_from.isoformat(),'effective_to':x.effective_to.isoformat() if x.effective_to else None} for x in items]

@router.post('/{employee_id}/compensation')
def set_compensation(employee_id:str,body:dict,db:Session=Depends(get_db),user:Employee=Depends(require_admin)):
 u=employee_or_404(db,employee_id)
 try:start=date.fromisoformat(body['effective_from']);monthly=Decimal(str(body['monthly_salary']));overtime=Decimal(str(body['overtime_hourly_rate']));late=Decimal(str(body['late_deduction_amount']))
 except (KeyError,ValueError,InvalidOperation):raise HTTPException(422,'Invalid compensation configuration')
 if min(monthly,overtime,late)<0:raise HTTPException(422,'Compensation amounts cannot be negative')
 prior=db.query(CompensationConfiguration).filter(CompensationConfiguration.employee_id==u.id,CompensationConfiguration.effective_from<start,CompensationConfiguration.effective_to.is_(None)).order_by(CompensationConfiguration.effective_from.desc()).first()
 overlap=db.query(CompensationConfiguration).filter(CompensationConfiguration.employee_id==u.id,CompensationConfiguration.effective_from<=start,CompensationConfiguration.effective_to.is_not(None),CompensationConfiguration.effective_to>=start).first()
 if overlap:raise HTTPException(409,'Compensation effective date overlaps an existing configuration')
 if prior:prior.effective_to=date.fromordinal(start.toordinal()-1)
 item=CompensationConfiguration(employee_id=u.id,monthly_salary=monthly,overtime_hourly_rate=overtime,late_deduction_amount=late,effective_from=start,created_by=user.id);db.add(item);audit(db,user,'set_compensation',u);db.commit();db.refresh(item);return {'id':str(item.id),'monthly_salary':str(item.monthly_salary),'overtime_hourly_rate':str(item.overtime_hourly_rate),'late_deduction_amount':str(item.late_deduction_amount),'effective_from':item.effective_from.isoformat(),'effective_to':None}
