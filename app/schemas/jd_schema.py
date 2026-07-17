from datetime import datetime

from pydantic import BaseModel, Field
from typing import List , Optional


class JobDescriptionRequest(BaseModel):
    job_description: str = Field(..., min_length=20)


class ExtractedJDResponse(BaseModel):
    job_role: str
    seniority_level: Optional[str] = None          # junior / mid / senior / lead
    required_skills: List[str]
    nice_to_have_skills: List[str] = []
    experience_required: Optional[str] = None
    qualifications: List[str] = []
    employment_type: Optional[str] = None           # full-time / contract / remote
    domain: Optional[str] = None                    # fintech / healthtech / etc.
    key_responsibilities: List[str] = []
    tools_and_platforms: List[str] = []             # Docker / AWS / Jira etc.
    location: Optional[str] = None                  # feeds GitHub location filter

#response schema for DB-saved JD.
class SavedJDResponse(BaseModel):
    id: int
    original_text: str
    job_role: str
    seniority_level: Optional[str] = None
    required_skills: List[str]
    nice_to_have_skills: List[str] = []
    experience_required: Optional[str] = None
    qualifications: List[str] = []
    employment_type: Optional[str] = None
    domain: Optional[str] = None
    key_responsibilities: List[str] = []
    tools_and_platforms: List[str] = []
    location: Optional[str] = None

    class Config:
        from_attributes = True

#For listing JDs from db in the frontend
class JDListItem(BaseModel):
    id: int
    job_role: str
    seniority_level: Optional[str] = None
    location: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True