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
        created_by_user_id: int,
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
            created_by_user_id   = created_by_user_id,
        )
        db.add(job_description)
        db.commit()
        db.refresh(job_description)
        return job_description
    
    def get_by_id(self, db: Session, jd_id: int, owner_user_id: int) -> JobDescription | None:
        """Scoped to owner — a recruiter can only fetch their own JDs."""
        return db.query(JobDescription).filter(
            JobDescription.id == jd_id,
            JobDescription.created_by_user_id == owner_user_id,
        ).first()
    
    def get_all(self, db: Session, owner_user_id: int, limit: int = 100) -> list[JobDescription]:
        return (
            db.query(JobDescription)
            .filter(JobDescription.created_by_user_id == owner_user_id)
            .order_by(JobDescription.created_at.desc())
            .limit(limit)
            .all()
        )

job_description_repository = JobDescriptionRepository()
