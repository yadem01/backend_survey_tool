from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Response(Base):
    __tablename__ = "response"

    r_id = Column(Integer, primary_key=True, index=True)
    q_id = Column(Integer, ForeignKey("survey.id"), nullable=False)
    p_id = Column(Integer, nullable=True)  # or link to a participants table if needed
    answer_txt = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime)
    time_spent = Column(Integer, nullable=True)
    meta = Column(String, nullable=True)  # store any other anti-cheat signals

    # relationship back to Survey (if you want easy access to question_text, etc.)
    survey = relationship("Survey", backref="responses")
