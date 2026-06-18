#defines the job_descriptions table
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func

from app.core.database import Base

class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(Integer,primary_key=True , index=True)
    original_text = Column(Text,nullable=False)

    job_role = Column(String(255),nullable=False)
    required_skills = Column(JSON,nullable=False)
    experience_required=Column(String(255),nullable=True)
    qualifications = Column(JSON,nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())