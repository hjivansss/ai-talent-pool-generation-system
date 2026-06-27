# Stores manually entered LinkedIn profiles in PostgreSQL.
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, Float, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class LinkedInProfileModel(Base):
    __tablename__ = "linkedin_profiles"

    id                    = Column(Integer, primary_key=True, index=True)
    full_name             = Column(String(255), nullable=False)
    headline              = Column(String(500), nullable=True)
    location              = Column(String(255), nullable=True)
    email                 = Column(String(255), nullable=True)
    phone                 = Column(String(50), nullable=True)
    profile_url           = Column(String(500), nullable=True)
    about                 = Column(Text, nullable=True)
    skills                = Column(JSON, nullable=True)        # ["Python", "FastAPI"]
    experience            = Column(JSON, nullable=True)        # list of experience dicts
    education             = Column(JSON, nullable=True)        # list of education dicts
    certifications        = Column(JSON, nullable=True)
    total_experience_years = Column(Float, nullable=True)
    current_role          = Column(String(255), nullable=True)
    current_company       = Column(String(255), nullable=True)
    open_to_work          = Column(Boolean, default=False)
    # tracks whether profile came from manual entry or ZIP upload
    source                 = Column(String(50), default="linkedin_manual")
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
