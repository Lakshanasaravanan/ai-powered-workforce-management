"""Idempotent local-only employee seed; run with PYTHONPATH=. python -m app.seed."""
import os
from sqlalchemy import func
from app.db.session import SessionLocal,Base,engine
from app.models.employee import Employee,Role
from app.core.security import hash_password
def main(session_factory=SessionLocal, create_schema=False, reset_dev_admin_password=False):
 if create_schema: Base.metadata.create_all(engine) # isolated-test convenience; Alembic owns runtime schema setup
 db=session_factory()
 try:
  seed_password=os.getenv('DEV_SEED_PASSWORD')
  entries=[('ADM001','InfoTech Admin','admin@infotech.local',Role.ADMIN,'AI Engineer','Platform'),('INF1002','Maya Manager','INF1002@infotech.local',Role.MANAGER,'Senior Engineer','Engineering'),('INF1001','Hari Employee','INF1001@infotech.local',Role.EMPLOYEE,'Junior Engineer','Engineering')]
  users={}
  for code,name,email,role,designation,department in entries:
   u=db.query(Employee).filter(func.lower(Employee.company_email)==email.lower()).first()
   if not u:
    if not seed_password: raise RuntimeError('DEV_SEED_PASSWORD is required to initialize development seed accounts')
    u=Employee(employee_code=code,full_name=name,company_email=email,role=role,designation=designation,department=department,password_hash=hash_password(seed_password),onboarding_completed=True,is_active=True);db.add(u);db.flush()
   elif code=='ADM001' and reset_dev_admin_password:
    # Explicit local-only recovery keeps routine idempotent seeding non-destructive.
    if not seed_password: raise RuntimeError('DEV_SEED_PASSWORD is required for explicit Admin recovery')
    u.password_hash=hash_password(seed_password);u.temporary_password_hash=None;u.onboarding_completed=True
   users[email]=u
  users['INF1001@infotech.local'].manager_id=users['INF1002@infotech.local'].id;db.commit()
 finally:db.close()
if __name__=='__main__':main(reset_dev_admin_password=os.getenv('RESET_DEV_ADMIN_PASSWORD','').lower() in {'1','true','yes'})
