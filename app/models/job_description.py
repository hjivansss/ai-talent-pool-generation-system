#defines the job_descriptions table
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id                   = Column(Integer, primary_key=True, index=True)
    original_text        = Column(Text, nullable=False)
    job_role             = Column(String(255), nullable=False)
    seniority_level      = Column(String(100), nullable=True)
    required_skills      = Column(JSON, nullable=False)
    nice_to_have_skills  = Column(JSON, nullable=True)
    experience_required  = Column(String(255), nullable=True)
    qualifications       = Column(JSON, nullable=True)
    employment_type      = Column(String(100), nullable=True)
    domain               = Column(String(255), nullable=True)
    key_responsibilities = Column(JSON, nullable=True)
    tools_and_platforms  = Column(JSON, nullable=True)
    location             = Column(String(255), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())

    # Per-recruiter data isolation — see router.py, every JD endpoint now
    # filters by this. 
    created_by_user_id   = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)