#Usage: handles saving extracted JD data into PostgreSQL
from sqlalchemy.orm import Session

from app.models.job_description import JobDescription
from app.schemas.jd_schema import ExtractedJDResponse

class JobDescriptionRepository:
    def create(
        self,
        db: Session,
        original_text: str,
        extracted_data: ExtractedJDResponse
        ) -> JobDescription:
    
        job_description = JobDescription(
                original_text=original_text,
                job_role=extracted_data.job_role,
                required_skills=extracted_data.required_skills,
                experience_required=extracted_data.experience_required,
                qualifications=extracted_data.qualifications
        )

        db.add(job_description)
        db.commit()
        db.refresh(job_description)

        return job_description
    
job_description_repository = JobDescriptionRepository()