# Phase 6 — talent_pools table.
# Stores the fully ranked and evaluated candidate list per JD.
# Generation runs once. Recruiters read from this table (paginated).

from sqlalchemy import Column, Integer, Float, JSON, DateTime, ForeignKey, String
from sqlalchemy.sql import func
from app.core.database import Base


class TalentPool(Base):
    __tablename__ = "talent_pools"

    id                = Column(Integer, primary_key=True, index=True)
    jd_id             = Column(Integer, ForeignKey("job_descriptions.id"), nullable=False, index=True)
    job_role          = Column(String(255), nullable=False)

    # Full ranked list stored as JSON — ordered by overall_fit_score desc
    # Each item is a CandidateEvaluation dict
    candidates        = Column(JSON, nullable=False)

    # Summary counts for quick display
    total_candidates  = Column(Integer, default=0)
    tier1_count       = Column(Integer, default=0)
    tier2_count       = Column(Integer, default=0)
    tier3_count       = Column(Integer, default=0)

    # Filter params used during generation — for audit and re-generation
    filter_params     = Column(JSON, nullable=True)

    generated_at      = Column(DateTime(timezone=True), server_default=func.now())
