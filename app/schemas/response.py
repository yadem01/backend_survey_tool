from typing import Optional
from pydantic import BaseModel
from datetime import datetime


# Shared properties
class ResponseBase(BaseModel):
    q_id: int
    p_id: Optional[int] = None
    answer_txt: str
    time_spent: Optional[int] = None
    meta: Optional[str] = None


# For creating new responses
class ResponseCreate(ResponseBase):
    pass


# For updating existing, if needed
class ResponseUpdate(ResponseBase):
    pass


# For reading from DB -> client
class ResponseInDBBase(ResponseBase):
    r_id: int
    timestamp: datetime

    class Config:
        orm_mode = True


# For returning to clients
class Response(ResponseInDBBase):
    pass
