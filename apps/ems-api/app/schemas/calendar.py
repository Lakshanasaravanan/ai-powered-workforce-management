from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.calendar import EventType
class EventWrite(BaseModel):
 model_config=ConfigDict(extra='forbid')
 title:str=Field(min_length=1,max_length=200); description:str|None=Field(default=None,max_length=5000); event_type:EventType; start_at:datetime; end_at:datetime; all_day:bool=False; location:str|None=Field(default=None,max_length=200)
 @model_validator(mode='after')
 def dates(self):
  if self.end_at<self.start_at: raise ValueError('end_at must not be before start_at')
  return self
