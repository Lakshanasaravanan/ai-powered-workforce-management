from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.calendar import EventType,EventScope
class EventWrite(BaseModel):
 model_config=ConfigDict(extra='forbid')
 title:str=Field(min_length=1,max_length=200); description:str|None=Field(default=None,max_length=5000); event_type:EventType; scope:EventScope=EventScope.PRIVATE; start_at:datetime; end_at:datetime; all_day:bool=False; location:str|None=Field(default=None,max_length=200)
 @model_validator(mode='after')
 def dates(self):
  if not self.title.strip(): raise ValueError('title must not be blank')
  if self.end_at<=self.start_at: raise ValueError('end_at must be later than start_at')
  return self

class HolidayWrite(BaseModel):
 model_config=ConfigDict(extra='forbid')
 holiday_date:date
 name:str=Field(min_length=1,max_length=160)
