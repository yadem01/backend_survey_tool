from sqlalchemy import JSON, Column, Integer, DateTime, func 
# from sqlalchemy.orm import relationship
from app.core.database import Base


class Response(Base):
    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, Foreign_key="survey.id")
    user_id = Column(Integer)
    question_id = Column(Integer, Foreign_key="survey_elements.id")
    response = Column(JSON)  # Kann Text oder Liste sein
    created_at = Column(DateTime, default=func.now())

    # __tablename__ = "response"

    # r_id = Column(Integer, primary_key=True, index=True)
    # q_id = Column(Integer, ForeignKey("survey.id"), nullable=False)
    # p_id = Column(Integer, nullable=True)  # or link to a participants table if needed
    # answer_txt = Column(String, nullable=False)
    # timestamp = Column(DateTime, default=datetime)
    # time_spent = Column(Integer, nullable=True)
    # meta = Column(String, nullable=True)  # store any other anti-cheat signals

    # # relationship back to Survey (if you want easy access to question_text, etc.)
    # survey = relationship("Survey", backref="responses")
