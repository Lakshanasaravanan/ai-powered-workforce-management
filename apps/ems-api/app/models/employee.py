import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import String,Boolean,DateTime,ForeignKey,Enum as SAEnum
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.db.session import Base
class Role(str,Enum): ADMIN='ADMIN'; MANAGER='MANAGER'; EMPLOYEE='EMPLOYEE'
class Employee(Base):
 __tablename__='employees'
 id:Mapped[uuid.UUID]=mapped_column(primary_key=True,default=uuid.uuid4)
 employee_code:Mapped[str]=mapped_column(String(32),unique=True,index=True)
 full_name:Mapped[str]=mapped_column(String(120)); company_email:Mapped[str]=mapped_column(String(255),unique=True,index=True)
 password_hash:Mapped[str]=mapped_column(String(255)); temporary_password_hash:Mapped[str|None]=mapped_column(String(255),nullable=True)
 role:Mapped[Role]=mapped_column(SAEnum(Role)); designation:Mapped[str]=mapped_column(String(100)); department:Mapped[str]=mapped_column(String(100))
 manager_id:Mapped[uuid.UUID|None]=mapped_column(ForeignKey('employees.id'),nullable=True); is_active:Mapped[bool]=mapped_column(Boolean,default=True); onboarding_completed:Mapped[bool]=mapped_column(Boolean,default=False)
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
