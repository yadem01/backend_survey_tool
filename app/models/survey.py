from typing import Text
from sqlalchemy import Column, DateTime, Integer, String, func
from app.core.database import Base


class Survey(Base):
    __tablename__ = "survey"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(String, default="draft")
    access_type = Column(String, default="private")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

