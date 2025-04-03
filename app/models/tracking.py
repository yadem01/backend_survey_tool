from sqlalchemy import Column, Integer, Boolean 
from app.core.database import Base

class UserTracking(Base):
    __tablename__ = "user_tracking"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    survey_id = Column(Integer)
    question_id = Column(Integer)
    time_taken = Column(Integer)
    copy_paste_detected = Column(Boolean, default=False)
    tab_switches = Column(Integer, default=0)
    window_blur = Column(Integer, default=0)
    idle_time = Column(Integer)
