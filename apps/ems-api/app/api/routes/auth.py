from fastapi import APIRouter,Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID
import jwt
from app.db.session import get_db
from app.models.employee import Employee
from app.core.config import Settings
from app.core.security import verify,hash_password,token
router=APIRouter(prefix='/api/v1/auth'); bearer=HTTPBearer()
def current(credentials:HTTPAuthorizationCredentials=Depends(bearer),db:Session=Depends(get_db)):
 try: ident=jwt.decode(credentials.credentials,Settings().jwt_secret,algorithms=[Settings().jwt_algorithm])['sub']
 except Exception: raise HTTPException(401,'Invalid authentication token')
 try:user=db.get(Employee,UUID(ident))
 except ValueError:raise HTTPException(401,'Invalid authentication token')
 if not user or not user.is_active: raise HTTPException(401,'Inactive or unknown employee')
 return user
@router.post('/login')
def login(body:dict,db:Session=Depends(get_db)):
 user=db.query(Employee).filter_by(employee_code=body.get('employee_code')).first()
 if not user or not user.is_active or not user.onboarding_completed or not verify(body.get('password',''),user.password_hash):raise HTTPException(401,'Invalid credentials')
 return {'access_token':token(str(user.id)),'token_type':'bearer','employee':summary(user)}
@router.post('/first-login')
def first_login(body:dict,db:Session=Depends(get_db)):
 user=db.query(Employee).filter_by(employee_code=body.get('employee_code')).first()
 if not user or not user.is_active or user.onboarding_completed or not user.temporary_password_hash or not verify(body.get('temporary_password',''),user.temporary_password_hash):raise HTTPException(401,'Invalid onboarding credential')
 user.password_hash=hash_password(body.get('new_password',''));user.temporary_password_hash=None;user.onboarding_completed=True;db.commit();return {'access_token':token(str(user.id)),'token_type':'bearer','employee':summary(user)}
@router.get('/me')
def me(user:Employee=Depends(current)):return summary(user)
def summary(u:Employee):return {'id':str(u.id),'employee_code':u.employee_code,'full_name':u.full_name,'company_email':u.company_email,'role':u.role,'designation':u.designation,'department':u.department,'manager_id':str(u.manager_id) if u.manager_id else None,'is_active':u.is_active}
