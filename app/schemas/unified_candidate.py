# Phase 5 — Unified candidate schema.
# Single format that GitHub and LinkedIn profiles both map into.
# This is what Phase 6 (matching) and Phase 7 (evaluation) consume.

from typing import List, Optional, Dict
from pydantic import BaseModel


class NormalizedExperience(BaseModel):
    title: str
    company: str
    duration: Optional[str] = None
    description: Optional[str] = None


class NormalizedEducation(BaseModel):
    degree: Optional[str] = None
    institution: str
    year: Optional[str] = None


class NormalizedProject(BaseModel):
    name: str
    description: Optional[str] = None
    url: str
    stars: int = 0
    forks: int = 0
    primary_language: Optional[str] = None
    topics: List[str] = []


class UnifiedCandidate(BaseModel):

    # ── Identity ────────────────────────────────────────────────────────────────
    name: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    # Profile links — one per source
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None        # blog / personal site from GitHub

    # ── Skills (merged from all sources) ────────────────────────────────────────
    # Flat deduplicated list — GitHub contributes language_list + all_topics,
    # LinkedIn contributes skills list. Both merged here.
    skills: List[str] = []

    # Language bytes from GitHub — kept for technical depth scoring in Phase 7
    top_languages: Dict[str, int] = {}

    # ── Experience ──────────────────────────────────────────────────────────────
    total_experience_years: Optional[float] = None
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    experience: List[NormalizedExperience] = []

    # ── Education ───────────────────────────────────────────────────────────────
    education: List[NormalizedEducation] = []
    certifications: List[str] = []

    # ── Technical signals (GitHub only — null for LinkedIn-only candidates) ─────
    github_repos_count: Optional[int] = None
    total_stars_earned: Optional[int] = None
    total_forks_earned: Optional[int] = None
    top_projects: List[NormalizedProject] = []
    active_days_last_month: Optional[int] = None
    account_age_years: Optional[float] = None

    # ── Inferred fields ─────────────────────────────────────────────────────────
    # Inferred from experience years + job titles + GitHub account age
    seniority_inferred: Optional[str] = None   # junior / mid / senior / lead

    # Inferred from company names, repo topics, LinkedIn headline
    domain_inferred: Optional[str] = None      # fintech / healthtech / etc.

    # ── Availability ────────────────────────────────────────────────────────────
    open_to_work: bool = False                 # hireable (GitHub) or open_to_work (LinkedIn)

    # ── Profile quality ─────────────────────────────────────────────────────────
    # % of key fields filled — higher = more reliable evaluation in Phase 7
    profile_completeness: float = 0.0          # 0.0 to 1.0

    # Which sources contributed to this profile
    sources: List[str] = []                    # e.g. ["github"], ["linkedin_zip"], ["github","linkedin_manual"]

    # ── Score placeholders (filled by Phase 7) ──────────────────────────────────
    skill_match_score: Optional[float] = None
    experience_match_score: Optional[float] = None
    overall_fit_score: Optional[float] = None