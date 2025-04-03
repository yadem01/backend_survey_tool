from sqlalchemy import Column, Integer, String
from app.core.database import Base


class Survey(Base):
    __tablename__ = "survey"

    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(String, nullable=False)
    # Could be an Enum column or just a string. Example:
    question_type = Column(String, nullable=False)
    options = Column(
        String, nullable=True
    )  # store multiple-choice options in JSON or CSV
    tracking_flags = Column(
        String, nullable=True
    )  # store JSON with flags { "trackTime": true }
    ordering = Column(Integer, nullable=False)
