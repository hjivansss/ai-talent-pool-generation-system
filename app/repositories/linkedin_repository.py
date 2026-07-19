# Saves and retrieves LinkedIn profiles from PostgreSQL.
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.linkedin_profile import LinkedInProfileModel
from app.schemas.candidate_schema import LinkedInProfile


class LinkedInRepository:

    def find_existing(self, db: Session, profile: LinkedInProfile) -> LinkedInProfileModel | None:
        """
        Identity check before insert: email first (most reliable), then
        full_name+profile_url as a fallback for profiles without an email.
        """
        if profile.email:
            existing = db.query(LinkedInProfileModel).filter(
                func.lower(LinkedInProfileModel.email) == profile.email.lower().strip()
            ).first()
            if existing:
                return existing
        if profile.full_name and profile.profile_url:
            return db.query(LinkedInProfileModel).filter(
                func.lower(LinkedInProfileModel.full_name) == profile.full_name.lower().strip(),
                LinkedInProfileModel.profile_url == profile.profile_url,
            ).first()
        return None

    def create_or_update(self, db: Session, profile: LinkedInProfile) -> tuple[LinkedInProfileModel, bool]:
        """
        Returns (record, is_new). Re-uploading the same profile (matched by
        email, or name+profile_url) updates the existing row in place instead
        of inserting a duplicate — previously there was no check at all here.
        """
        existing = self.find_existing(db, profile)
        fields = dict(
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
            source                 = profile.source,
        )
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing, False

        record = LinkedInProfileModel(**fields)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record, True

    # Kept for any other callers — now routes through create_or_update so
    # every insertion path gets the dedup check, not just the two upload
    # endpoints that were updated to call create_or_update directly.
    def create(self, db: Session, profile: LinkedInProfile) -> LinkedInProfileModel:
        record, _ = self.create_or_update(db, profile)
        return record

    def get_open_to_work(self, db: Session) -> list[LinkedInProfileModel]:
        """Fetch all candidates marked open to work — primary recruiter filter."""
        return db.query(LinkedInProfileModel).filter(
            LinkedInProfileModel.open_to_work == True
        ).all()

    def get_all(self, db: Session, limit: int = 50) -> list[LinkedInProfileModel]:
        return db.query(LinkedInProfileModel).limit(limit).all()


linkedin_repository = LinkedInRepository()
