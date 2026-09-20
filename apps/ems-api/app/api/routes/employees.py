from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from uuid import UUID
from app.db.session import get_db
from app.models.employee import Employee,Role
from app.core.security import hash_password
from app.api.dependencies import get_current_user,require_admin,require_manager
from app.api.routes.auth import summary
router=APIRouter(prefix='/api/v1/employees')
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
 if db.query(Employee).filter(or_(Employee.company_email==body.get('company_email'),Employee.employee_code==body.get('employee_code'))).first():raise HTTPException(409,'Duplicate employee code or company email')
 temp=body.get('temporary_password','welcome-change-me')
 u=Employee(employee_code=body['employee_code'],full_name=body['full_name'],company_email=body['company_email'],role=Role(body['role']),designation=body['designation'],department=body['department'],manager_id=validate_manager(db,body.get('manager_id')),password_hash=hash_password('disabled'),temporary_password_hash=hash_password(temp))
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
 if 'manager_id' in body:u.manager_id=validate_manager(db,body['manager_id'],u.id)
 db.commit();return summary(u)
