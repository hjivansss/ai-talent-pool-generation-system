from typing import List, Optional

from pydantic import BaseModel


class CandidateSearchRequest(BaseModel):
    skills: List[str]
    location: Optional[str] = None
    limit: int = 10


class GitHubCandidateProfile(BaseModel):
    username: str
    profile_url: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    public_repos: Optional[int] = None
    followers: Optional[int] = None
    source: str = "github"


class CandidateSearchResponse(BaseModel):
    query: str
    total_found: int
    candidates: List[GitHubCandidateProfile]