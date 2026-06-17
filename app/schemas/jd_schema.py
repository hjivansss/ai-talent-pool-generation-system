from pydantic import BaseModel, Field
from typing import List


class JobDescriptionRequest(BaseModel):
    job_description: str = Field(..., min_length=20)


class ExtractedJDResponse(BaseModel):
    job_role: str
    required_skills: List[str]
    experience_required: str
    qualifications: List[str]