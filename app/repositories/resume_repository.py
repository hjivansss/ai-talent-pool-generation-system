# Saves and retrieves resume profiles from PostgreSQL.
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.resume import ResumeModel
from app.schemas.candidate_schema import LinkedInProfile


class ResumeRepository:

    def find_existing(self, db: Session, profile: LinkedInProfile) -> ResumeModel | None:
        """Identity check before insert: email first, then full_name as fallback."""
        if profile.email:
            existing = db.query(ResumeModel).filter(
                func.lower(ResumeModel.email) == profile.email.lower().strip()
            ).first()
            if existing:
                return existing
        if profile.full_name:
            return db.query(ResumeModel).filter(
                func.lower(ResumeModel.full_name) == profile.full_name.lower().strip()
            ).first()
        return None

    def create_or_update(
        self,
        db: Session,
        profile: LinkedInProfile,
        file_name: str | None = None,
        file_url: str | None = None,
        uploaded_by_user_id: int | None = None,
        candidate_owner_user_id: int | None = None,
    ) -> tuple[ResumeModel, bool]:
        """
        Returns (record, is_new). Re-uploading the same resume (matched by
        email, or full_name as fallback) updates the existing row instead of
        inserting a duplicate.

        Ownership fields are overwritten on every call, including re-uploads
        — this matches the "always overwrite in place" decision: whoever
        uploads most recently becomes the new uploaded_by_user_id, even if a
        different party uploaded it originally. candidate_owner_user_id is
        only passed when the uploader IS the candidate themselves (see
        router.py) — a recruiter re-uploading does NOT clear an existing
        candidate's ownership, since recruiter uploads pass None here and we
        only overwrite candidate_owner_user_id when a non-None value is given.
        """
        existing = self.find_existing(db, profile)
        fields = dict(
            full_name              = profile.full_name,
            headline                = profile.headline,
            location               = profile.location,
            email                   = profile.email,
            phone                   = profile.phone,
            profile_url             = profile.profile_url,
            about                   = profile.about,
            skills                  = profile.skills,
            experience              = [e.model_dump() for e in profile.experience],
            education               = [e.model_dump() for e in profile.education],
            certifications          = profile.certifications,
            total_experience_years  = profile.total_experience_years,
            current_role            = profile.current_role,
            current_company         = profile.current_company,
            open_to_work            = profile.open_to_work,
            file_name               = file_name,
            source                  = "resume",
            uploaded_by_user_id     = uploaded_by_user_id,
        )
        if file_url is not None:
            fields["file_url"] = file_url
        if candidate_owner_user_id is not None:
            fields["candidate_owner_user_id"] = candidate_owner_user_id

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing, False

        record = ResumeModel(**fields)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record, True

    # Kept for any other callers — routes through create_or_update.
    def create(self, db: Session, profile: LinkedInProfile, file_name: str | None = None) -> ResumeModel:
        record, _ = self.create_or_update(db, profile, file_name)
        return record

    def get_all(self, db: Session, limit: int = 100) -> list[ResumeModel]:
        return db.query(ResumeModel).limit(limit).all()


resume_repository = ResumeRepository()
