"""Idempotent local-only employee seed; run with PYTHONPATH=. python -m app.seed."""
import os
from app.db.session import SessionLocal,Base,engine
from app.models.employee import Employee,Role
from app.core.security import hash_password
def main(session_factory=SessionLocal, create_schema=False):
 if create_schema: Base.metadata.create_all(engine) # isolated-test convenience; Alembic owns runtime schema setup
 db=session_factory()
 try:
  entries=[('ADM001','InfoTech Admin','admin@infotech.local',Role.ADMIN,'AI Engineer','Platform'),('INF1002','Maya Manager','INF1002@infotech.local',Role.MANAGER,'Senior Engineer','Engineering'),('INF1001','Hari Employee','INF1001@infotech.local',Role.EMPLOYEE,'Junior Engineer','Engineering')]
  users={}
  for code,name,email,role,designation,department in entries:
   u=db.query(Employee).filter_by(company_email=email).first()
   if not u:
    u=Employee(employee_code=code,full_name=name,company_email=email,role=role,designation=designation,department=department,password_hash=hash_password(os.getenv('DEV_SEED_PASSWORD','change-me-local-only')),onboarding_completed=True,is_active=True);db.add(u);db.flush()
   users[email]=u
  users['INF1001@infotech.local'].manager_id=users['INF1002@infotech.local'].id;db.commit()
 finally:db.close()
if __name__=='__main__':main()
