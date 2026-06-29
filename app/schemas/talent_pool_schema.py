# Phase 6 — Talent pool request and response schemas.

from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime


# ── Request ─────────────────────────────────────────────────────────────────────

class TalentPoolRequest(BaseModel):
    jd_id: int                          # saved JD to evaluate against
    location: Optional[str] = None      # overrides JD location if provided
    limit: int = 15                     # max GitHub candidates to fetch (hard cap 20)
    min_score: float = 0.3              # Stage 1 filter threshold (0.0 to 1.0)
    page: int = 1                       # pagination — which page to return
    page_size: int = 10                 # candidates per page


class TalentPoolViewRequest(BaseModel):
    page: int = 1
    page_size: int = 10


# ── Per-candidate evaluation result ─────────────────────────────────────────────

class SkillGap(BaseModel):
    skill: str
    criticality: str                    # "critical" / "moderate" / "minor"


class CandidateEvaluation(BaseModel):
    # Identity
    name: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    sources: List[str] = []

    # Skills snapshot
    skills: List[str] = []
    top_languages: Dict[str, int] = {}
    top_projects: List[dict] = []

    # Experience snapshot
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    total_experience_years: Optional[float] = None
    seniority_inferred: Optional[str] = None

    # Stage 1 scores (rule-based)
    skill_match_score: float = 0.0      # 0.0 to 1.0
    experience_match_score: float = 0.0
    tools_match_score: float = 0.0
    matched_skills: List[str] = []
    skill_gaps: List[SkillGap] = []

    # Stage 2 scores (Ollama)
    overall_fit_score: float = 0.0      # 0 to 100
    recommendation: str = ""            # Strong Match / Good Match / Partial Match
    tier: int = 3                       # 1 / 2 / 3
    strengths: List[str] = []
    justification: str = ""
    skill_gap_analysis: str = ""

    # Profile quality
    profile_completeness: float = 0.0
    open_to_work: bool = False


# ── Talent pool response ─────────────────────────────────────────────────────────

class TalentPoolResponse(BaseModel):
    pool_id: int
    jd_id: int
    job_role: str
    generated_at: datetime
    total_candidates: int
    page: int
    page_size: int
    total_pages: int
    candidates: List[CandidateEvaluation]


class TalentPoolSummary(BaseModel):
    pool_id: int
    jd_id: int
    job_role: str
    generated_at: datetime
    total_candidates: int
    tier1_count: int
    tier2_count: int
    tier3_count: int
