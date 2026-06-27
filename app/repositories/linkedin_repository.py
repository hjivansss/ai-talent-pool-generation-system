# Saves and retrieves LinkedIn profiles from PostgreSQL.
from sqlalchemy.orm import Session
from app.models.linkedin_profile import LinkedInProfileModel
from app.schemas.candidate_schema import LinkedInProfile


class LinkedInRepository:
    def create(self, db: Session, profile: LinkedInProfile) -> LinkedInProfileModel:
        record = LinkedInProfileModel(
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
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get_open_to_work(self, db: Session) -> list[LinkedInProfileModel]:
        """Fetch all candidates marked open to work — primary recruiter filter."""
        return db.query(LinkedInProfileModel).filter(
            LinkedInProfileModel.open_to_work == True
        ).all()

    def get_all(self, db: Session, limit: int = 50) -> list[LinkedInProfileModel]:
        return db.query(LinkedInProfileModel).limit(limit).all()


linkedin_repository = LinkedInRepository()
