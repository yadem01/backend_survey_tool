from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from app.core.database import Base

class SurveyParticipant(Base):
    __tablename__ = "survey_participants"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("survey.id"))
    user_id = Column(Integer)
    prolific_id = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    suspicious_behavior = Column(Boolean, default=False)
    arc_passed = Column(Boolean, default=False)
    consent_given = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    end_time = Column(DateTime, nullable=True)
