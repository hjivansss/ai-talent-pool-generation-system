from typing import List, Optional, Dict
from pydantic import BaseModel


# ── GitHub ─────────────────────────────────────────────────────────────────────

class CandidateSearchRequest(BaseModel):
    skills: List[str]
    location: Optional[str] = None
    limit: int = 10


class GitHubRepoSummary(BaseModel):
    name: str
    description: Optional[str] = None
    url: str
    stars: int = 0
    forks: int = 0
    primary_language: Optional[str] = None
    topics: List[str] = []
    is_fork: bool = False
    last_pushed: Optional[str] = None


class GitHubCandidateProfile(BaseModel):
    # Identity
    username: str
    name: Optional[str] = None
    profile_url: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    blog: Optional[str] = None

    # Stats
    public_repos: Optional[int] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    total_stars_earned: int = 0
    total_forks_earned: int = 0

    # Tech stack — derived from all repos
    top_languages: Dict[str, int] = {}     # {language: bytes_written}
    language_list: List[str] = []          # ranked list for display

    # Projects
    top_repos: List[GitHubRepoSummary] = []
    all_topics: List[str] = []

    # Activity signals
    recent_activity_types: List[str] = []
    active_days_last_month: int = 0

    # Hiring signals
    hireable: Optional[bool] = None
    account_age_years: Optional[float] = None

    source: str = "github"


class CandidateSearchResponse(BaseModel):
    query: str
    total_found: int
    candidates: List[GitHubCandidateProfile]


# ── LinkedIn Manual ─────────────────────────────────────────────────────────────

class LinkedInExperience(BaseModel):
    title: str
    company: str
    duration: Optional[str] = None
    description: Optional[str] = None


class LinkedInEducation(BaseModel):
    degree: Optional[str] = None
    institution: str
    year: Optional[str] = None


class LinkedInProfile(BaseModel):
    # Identity
    full_name: str
    headline: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    profile_url: Optional[str] = None

    # Professional
    about: Optional[str] = None
    skills: List[str] = []
    experience: List[LinkedInExperience] = []
    education: List[LinkedInEducation] = []
    certifications: List[str] = []

    # Key hiring signals
    total_experience_years: Optional[float] = None
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    open_to_work: bool = False

    source: str = "linkedin_manual"

# ── LinkedIn request/response wrappers ──────────────────────────────────────────

class LinkedInIngestRequest(BaseModel):
    profiles: List[LinkedInProfile]


class LinkedInIngestResponse(BaseModel):
    total_saved: int
    profiles: List[LinkedInProfile]


class LinkedInZipUploadResponse(BaseModel):
    message: str
    profile: LinkedInProfile

class ResumeUploadResponse(BaseModel):
    message: str
    profile: LinkedInProfile   # resume parses into same structure as LinkedIn