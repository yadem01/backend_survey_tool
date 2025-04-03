from typing import Text
from sqlalchemy import JSON, Column, ForeignKey, Integer, String
from app.core.database import Base

class SurveyElement(Base):
    __tablename__ = "survey_elements"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("survey.id"))
    element_type = Column(String)  # question, info, section, welcome
    element_text = Column(Text)
    question_type = Column(String, nullable=True)
    options = Column(JSON, nullable=True)
    ordering = Column(Integer)
    page = Column(Integer)