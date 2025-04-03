from typing import Optional
from pydantic import BaseModel


# Shared properties
class SurveyBase(BaseModel):
    question_text: str
    question_type: str
    options: Optional[str] = None
    tracking_flags: Optional[str] = None
    ordering: int


# For creating a new survey question
class SurveyCreate(SurveyBase):
    pass


# For updating an existing survey question
class SurveyUpdate(SurveyBase):
    pass


# For reading (DB -> API response)
class SurveyInDBBase(SurveyBase):
    id: int

    class Config:
        orm_mode = True


# For returning to clients
class Survey(SurveyInDBBase):
    pass
