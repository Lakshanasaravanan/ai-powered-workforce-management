import uuid
from datetime import date,datetime
from decimal import Decimal
from enum import Enum
from sqlalchemy import String,Boolean,DateTime,Date,ForeignKey,Enum as SAEnum,Numeric,CheckConstraint
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
 manager_id:Mapped[uuid.UUID|None]=mapped_column(ForeignKey('employees.id'),nullable=True); is_active:Mapped[bool]=mapped_column(Boolean,default=True); archived_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); onboarding_completed:Mapped[bool]=mapped_column(Boolean,default=False)
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)

class CompensationConfiguration(Base):
 __tablename__='compensation_configurations'
 __table_args__=(CheckConstraint('effective_to IS NULL OR effective_to >= effective_from',name='ck_compensation_dates'),)
 id:Mapped[uuid.UUID]=mapped_column(primary_key=True,default=uuid.uuid4)
 employee_id:Mapped[uuid.UUID]=mapped_column(ForeignKey('employees.id'),index=True)
 monthly_salary:Mapped[Decimal]=mapped_column(Numeric(12,2),nullable=False)
 overtime_hourly_rate:Mapped[Decimal]=mapped_column(Numeric(12,2),nullable=False)
 late_deduction_amount:Mapped[Decimal]=mapped_column(Numeric(12,2),nullable=False)
 effective_from:Mapped[date]=mapped_column(Date,nullable=False,index=True)
 effective_to:Mapped[date|None]=mapped_column(Date,nullable=True)
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,nullable=False)
 created_by:Mapped[uuid.UUID]=mapped_column(ForeignKey('employees.id'),nullable=False)
