#Usage: handles saving extracted JD data into PostgreSQL
from sqlalchemy.orm import Session

from app.models.job_description import JobDescription
from app.schemas.jd_schema import ExtractedJDResponse

class JobDescriptionRepository:
    def create(
        self,
        db: Session,
        original_text: str,
        extracted_data: ExtractedJDResponse,
    ) -> JobDescription:
        job_description = JobDescription(
            original_text        = original_text,
            job_role             = extracted_data.job_role,
            seniority_level      = extracted_data.seniority_level,
            required_skills      = extracted_data.required_skills,
            nice_to_have_skills  = extracted_data.nice_to_have_skills,
            experience_required  = extracted_data.experience_required,
            qualifications       = extracted_data.qualifications,
            employment_type      = extracted_data.employment_type,
            domain               = extracted_data.domain,
            key_responsibilities = extracted_data.key_responsibilities,
            tools_and_platforms  = extracted_data.tools_and_platforms,
            location             = extracted_data.location,
        )
        db.add(job_description)
        db.commit()
        db.refresh(job_description)
        return job_description
    
    def get_by_id(self, db: Session, jd_id: int) -> JobDescription | None:
        return db.query(JobDescription).filter(JobDescription.id == jd_id).first()

job_description_repository = JobDescriptionRepository()
