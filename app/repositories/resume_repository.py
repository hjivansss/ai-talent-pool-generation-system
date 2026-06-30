# Saves and retrieves resume profiles from PostgreSQL.
from sqlalchemy.orm import Session
from app.models.resume import ResumeModel
from app.schemas.candidate_schema import LinkedInProfile


class ResumeRepository:
    def create(
        self,
        db: Session,
        profile: LinkedInProfile,
        file_name: str | None = None,
    ) -> ResumeModel:
        record = ResumeModel(
            full_name              = profile.full_name,
            headline               = profile.headline,
            location               = profile.location,
            email                  = profile.email,
            phone                  = profile.phone,
            profile_url            = profile.profile_url,
            about                  = profile.about,
            skills                 = profile.skills,
            experience             = [e.model_dump() for e in profile.experience],
            education              = [e.model_dump() for e in profile.education],
            certifications         = profile.certifications,
            total_experience_years = profile.total_experience_years,
            current_role           = profile.current_role,
            current_company        = profile.current_company,
            open_to_work           = profile.open_to_work,
            file_name              = file_name,
            source                 = "resume",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get_all(self, db: Session, limit: int = 100) -> list[ResumeModel]:
        return db.query(ResumeModel).limit(limit).all()


resume_repository = ResumeRepository()
