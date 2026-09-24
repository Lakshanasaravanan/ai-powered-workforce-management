import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
class EventType(str,Enum): MEETING='MEETING'; TRAINING='TRAINING'; COMPANY_EVENT='COMPANY_EVENT'; HOLIDAY='HOLIDAY'; GENERAL='GENERAL'
class CalendarEvent(Base):
 __tablename__='calendar_events'
 id:Mapped[uuid.UUID]=mapped_column(primary_key=True,default=uuid.uuid4)
 title:Mapped[str]=mapped_column(String(200)); description:Mapped[str|None]=mapped_column(Text,nullable=True); event_type:Mapped[EventType]=mapped_column(SAEnum(EventType))
 start_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); end_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); all_day:Mapped[bool]=mapped_column(Boolean,default=False); location:Mapped[str|None]=mapped_column(String(200),nullable=True)
 created_by:Mapped[uuid.UUID]=mapped_column(ForeignKey('employees.id')); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=datetime.utcnow,onupdate=datetime.utcnow)
