import os
os.environ['DATABASE_URL']='sqlite:///./phase2-test.db'
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db.session import Base,get_db
from app.models.employee import Employee,Role
from app.core.security import hash_password,token
import jwt
from datetime import datetime,timedelta,timezone
from app.core.config import Settings
from app import seed

engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Session=sessionmaker(engine);Base.metadata.create_all(engine)
def db_override():
 db=Session()
 try:yield db
 finally:db.close()
app.dependency_overrides[get_db]=db_override
client=TestClient(app)
def make(code,role=Role.EMPLOYEE,active=True,onboard=True,manager_id=None):
 db=Session();u=Employee(employee_code=code,full_name=code,company_email=f'{code}@infotech.local',role=role,designation='Engineer',department='Engineering',password_hash=hash_password('test-password'),temporary_password_hash=hash_password('temporary-password'),onboarding_completed=onboard,is_active=active,manager_id=manager_id);db.add(u);db.commit();db.refresh(u);db.close();return u
def headers(user):return {'Authorization':'Bearer '+token(str(user.id))}
def setup():
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine);return make('ADMIN',Role.ADMIN),make('MANAGER',Role.MANAGER),make('EMPLOYEE')
def test_login_me_and_invalid_password():
 _,_,u=setup();assert client.post('/api/v1/auth/login',json={'employee_code':'EMPLOYEE','password':'test-password'}).status_code==200;assert client.post('/api/v1/auth/login',json={'employee_code':'EMPLOYEE','password':'wrong'}).status_code==401;assert client.get('/api/v1/auth/me',headers=headers(u)).json()['employee_code']=='EMPLOYEE';assert client.get('/api/v1/auth/me').status_code==401
def test_first_login_invalidates_temp():
 setup();u=make('NEW',onboard=False);body={'employee_code':'NEW','temporary_password':'temporary-password','new_password':'new-password'};assert client.post('/api/v1/auth/first-login',json=body).status_code==200;assert client.post('/api/v1/auth/first-login',json=body).status_code==401;assert client.post('/api/v1/auth/login',json={'employee_code':'NEW','password':'new-password'}).status_code==200
def test_admin_rbac_search_and_inactive():
 admin,manager,u=setup();payload={'employee_code':'NEW','full_name':'New','company_email':'NEW@infotech.local','role':'EMPLOYEE','designation':'Engineer','department':'Engineering'};assert client.post('/api/v1/employees',json=payload,headers=headers(admin)).status_code==200;assert client.post('/api/v1/employees',json=payload,headers=headers(admin)).status_code==409;assert client.post('/api/v1/employees',json=payload,headers=headers(u)).status_code==403;assert client.get('/api/v1/employees/search?q=EMP',headers=headers(u)).status_code==200
def test_inactive_and_direct_reports():
 admin,manager,u=setup();db=Session();u.manager_id=manager.id;u.is_active=False;db.merge(u);db.commit();db.close();assert client.post('/api/v1/auth/login',json={'employee_code':'EMPLOYEE','password':'test-password'}).status_code==401;assert client.get('/api/v1/auth/me',headers=headers(u)).status_code==401;assert len(client.get('/api/v1/employees/me/direct-reports',headers=headers(manager)).json())==0;assert client.get('/api/v1/employees/me/direct-reports',headers=headers(u)).status_code==401
def test_my_manager_uses_authenticated_identity_only():
 admin,manager,u=setup();db=Session();u.manager_id=manager.id;db.merge(u);db.commit();db.close();response=client.get('/api/v1/employees/me/manager?employee_id='+str(admin.id),headers=headers(u));assert response.status_code==200 and response.json()['manager']['id']==str(manager.id);assert client.get('/api/v1/employees/me/manager',headers=headers(admin)).json()=={'manager':None}
def test_manager_validation_and_cycles():
 admin,manager,u=setup();db=Session();u.manager_id=manager.id;db.merge(u);db.commit();assert client.patch('/api/v1/employees/'+str(manager.id),json={'manager_id':str(u.id)},headers=headers(admin)).status_code==422;assert client.patch('/api/v1/employees/'+str(u.id),json={'manager_id':'missing'},headers=headers(admin)).status_code==422;assert client.patch('/api/v1/employees/'+str(u.id),json={'manager_id':str(u.id)},headers=headers(admin)).status_code==422;db.close()
def test_edit_status_and_jwt_rejections():
 admin,manager,u=setup();assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer invalid'}).status_code==401;assert client.patch('/api/v1/employees/'+str(u.id),json={'designation':'AI Engineer','is_active':False},headers=headers(admin)).status_code==200;assert client.post('/api/v1/auth/login',json={'employee_code':'EMPLOYEE','password':'test-password'}).status_code==401;assert client.patch('/api/v1/employees/'+str(u.id),json={'is_active':True},headers=headers(admin)).status_code==200;assert client.post('/api/v1/auth/login',json={'employee_code':'EMPLOYEE','password':'test-password'}).status_code==200
def test_password_storage_and_duplicate_fields():
 admin,_,u=setup();db=Session();stored=db.get(Employee,u.id);assert stored.password_hash.startswith('$argon2') and stored.password_hash!='test-password';db.close();base={'employee_code':'NEW','full_name':'New','company_email':'NEW@infotech.local','role':'EMPLOYEE','designation':'Engineer','department':'Engineering'};assert client.post('/api/v1/employees',json=base,headers=headers(admin)).status_code==200;assert client.post('/api/v1/employees',json={**base,'company_email':'OTHER@infotech.local'},headers=headers(admin)).status_code==409;assert client.post('/api/v1/employees',json={**base,'employee_code':'OTHER'},headers=headers(admin)).status_code==409
def test_expired_and_malformed_subject_tokens():
 _,_,u=setup();s=Settings();expired=jwt.encode({'sub':str(u.id),'exp':datetime.now(timezone.utc)-timedelta(seconds=1)},s.jwt_secret,algorithm=s.jwt_algorithm);bad=jwt.encode({'sub':'not-a-uuid','exp':datetime.now(timezone.utc)+timedelta(minutes=1)},s.jwt_secret,algorithm=s.jwt_algorithm);assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+expired}).status_code==401;assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+bad}).status_code==401
def test_inactive_first_login_does_not_consume_credential():
 _,_,u=setup();db=Session();u.onboarding_completed=False;u.is_active=False;u.temporary_password_hash=hash_password('temporary-password');before=u.password_hash;db.merge(u);db.commit();db.close();body={'employee_code':'EMPLOYEE','temporary_password':'temporary-password','new_password':'new-password'};assert client.post('/api/v1/auth/first-login',json=body).status_code==401;db=Session();saved=db.get(Employee,u.id);assert not saved.onboarding_completed and saved.password_hash==before and saved.temporary_password_hash;db.close()
def test_multi_node_cycle_rejected_and_hierarchy_preserved():
 admin,b,c=setup();db=Session();a=make('A',Role.MANAGER);db=Session();a.manager_id=b.id;b.manager_id=c.id;db.merge(a);db.merge(b);db.commit();db.close();assert client.patch('/api/v1/employees/'+str(c.id),json={'manager_id':str(a.id)},headers=headers(admin)).status_code==422;db=Session();assert db.get(Employee,a.id).manager_id==b.id and db.get(Employee,b.id).manager_id==c.id and db.get(Employee,c.id).manager_id is None;db.close()
def test_seed_is_idempotent_and_uses_employee_email_convention(monkeypatch):
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine);monkeypatch.setattr(seed,'engine',engine);seed.main(Session,create_schema=False);seed.main(Session,create_schema=False);db=Session();rows=db.query(Employee).all();by={x.employee_code:x for x in rows};assert len(rows)==3 and by['INF1001'].manager_id==by['INF1002'].id;assert by['INF1001'].company_email.split('@')[0]==by['INF1001'].employee_code and by['INF1002'].company_email.split('@')[0]==by['INF1002'].employee_code and by['ADM001'].role==Role.ADMIN;db.close()
