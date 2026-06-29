# Phase 6 — Saves and retrieves talent pools from PostgreSQL.

from sqlalchemy.orm import Session
from app.models.talent_pool import TalentPool
from app.schemas.talent_pool_schema import CandidateEvaluation


class TalentPoolRepository:

    def create(
        self,
        db: Session,
        jd_id: int,
        job_role: str,
        candidates: list[CandidateEvaluation],
        filter_params: dict,
    ) -> TalentPool:
        tier1 = sum(1 for c in candidates if c.tier == 1)
        tier2 = sum(1 for c in candidates if c.tier == 2)
        tier3 = sum(1 for c in candidates if c.tier == 3)

        pool = TalentPool(
            jd_id            = jd_id,
            job_role         = job_role,
            candidates       = [c.model_dump() for c in candidates],
            total_candidates = len(candidates),
            tier1_count      = tier1,
            tier2_count      = tier2,
            tier3_count      = tier3,
            filter_params    = filter_params,
        )
        db.add(pool)
        db.commit()
        db.refresh(pool)
        return pool

    def get_by_id(self, db: Session, pool_id: int) -> TalentPool | None:
        return db.query(TalentPool).filter(TalentPool.id == pool_id).first()

    def get_by_jd_id(self, db: Session, jd_id: int) -> list[TalentPool]:
        """Returns all pools generated for a JD, newest first."""
        return (
            db.query(TalentPool)
            .filter(TalentPool.jd_id == jd_id)
            .order_by(TalentPool.generated_at.desc())
            .all()
        )

    def get_latest_by_jd_id(self, db: Session, jd_id: int) -> TalentPool | None:
        """Returns the most recently generated pool for a JD."""
        return (
            db.query(TalentPool)
            .filter(TalentPool.jd_id == jd_id)
            .order_by(TalentPool.generated_at.desc())
            .first()
        )


talent_pool_repository = TalentPoolRepository()
