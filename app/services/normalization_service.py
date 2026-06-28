# Phase 5 — Candidate Normalization Service.
# Maps GitHub and LinkedIn raw profiles into UnifiedCandidate.
# Handles deduplication, seniority inference, domain inference,
# and profile completeness scoring.

from typing import Optional
from app.schemas.candidate_schema import GitHubCandidateProfile, LinkedInProfile
from app.schemas.unified_candidate import (
    UnifiedCandidate,
    NormalizedExperience,
    NormalizedEducation,
    NormalizedProject,
)


# ── Seniority inference ─────────────────────────────────────────────────────────

SENIORITY_TITLE_SIGNALS = {
    "lead":   ["lead", "principal", "staff", "architect", "head of", "vp", "director"],
    "senior": ["senior", "sr.", "sr ", "manager"],
    "junior": ["junior", "jr.", "jr ", "intern", "trainee", "fresher", "entry"],
}

def _infer_seniority(
    experience_years: Optional[float],
    current_role: Optional[str],
    account_age_years: Optional[float],
) -> Optional[str]:
    """
    Infers seniority from experience years and role title.
    Falls back to GitHub account age if no other signal.
    """
    # Check title keywords first — most reliable signal
    if current_role:
        role_lower = current_role.lower()
        for level, keywords in SENIORITY_TITLE_SIGNALS.items():
            if any(kw in role_lower for kw in keywords):
                return level

    # Use experience years
    years = experience_years or (account_age_years * 0.6 if account_age_years else None)
    if years is not None:
        if years < 2:
            return "junior"
        elif years < 5:
            return "mid"
        elif years < 10:
            return "senior"
        else:
            return "lead"

    return None


# ── Domain inference ────────────────────────────────────────────────────────────

DOMAIN_SIGNALS: dict[str, list[str]] = {
    "fintech":     ["bank", "finance", "payment", "trading", "fintech", "crypto", "wallet", "lending"],
    "healthtech":  ["health", "medical", "hospital", "clinical", "pharma", "biotech", "ehr"],
    "edtech":      ["education", "learning", "edtech", "school", "course", "tutoring", "lms"],
    "ecommerce":   ["ecommerce", "retail", "shopify", "marketplace", "commerce", "shopping"],
    "devtools":    ["developer tools", "devops", "infrastructure", "platform", "sdk", "cli", "api"],
    "ai/ml":       ["machine learning", "ai", "deep learning", "nlp", "computer vision", "data science"],
    "gamedev":     ["game", "gaming", "unity", "unreal", "gamedev"],
    "cybersecurity": ["security", "cybersecurity", "pentest", "infosec", "vulnerability"],
}

def _infer_domain(
    headline: Optional[str],
    about: Optional[str],
    bio: Optional[str],
    topics: list[str],
    experience: list,
) -> Optional[str]:
    """
    Infers industry domain from text signals across all sources.
    """
    # Build one combined text blob to scan
    text_parts = [
        headline or "",
        about or "",
        bio or "",
        " ".join(topics),
        " ".join(e.company.lower() if hasattr(e, "company") else "" for e in experience),
    ]
    text = " ".join(text_parts).lower()

    for domain, signals in DOMAIN_SIGNALS.items():
        if any(signal in text for signal in signals):
            return domain

    return None


# ── Skill merging ───────────────────────────────────────────────────────────────

def _merge_skills(
    language_list: list[str],
    topics: list[str],
    linkedin_skills: list[str],
) -> list[str]:
    """
    Merges skills from all sources into one deduplicated ranked list.
    Order: LinkedIn skills first (explicit), then GitHub languages, then topics.
    """
    seen: set[str] = set()
    merged: list[str] = []

    for skill in linkedin_skills + language_list + topics:
        normalized = skill.strip()
        key = normalized.lower()
        if key and key not in seen:
            seen.add(key)
            merged.append(normalized)

    return merged[:30]


# ── Profile completeness ────────────────────────────────────────────────────────

def _compute_completeness(candidate: UnifiedCandidate) -> float:
    """
    Scores how complete a unified profile is (0.0 to 1.0).
    Each key field that is filled contributes equally.
    Phase 7 uses this to weight evaluation confidence.
    """
    key_fields = [
        candidate.name,
        candidate.location,
        candidate.skills,
        candidate.total_experience_years,
        candidate.current_role,
        candidate.experience,
        candidate.education,
        candidate.top_projects or candidate.github_repos_count,
        candidate.seniority_inferred,
        candidate.email or candidate.github_url or candidate.linkedin_url,
    ]
    filled = sum(1 for f in key_fields if f)
    return round(filled / len(key_fields), 2)


# ── Main normalization service ──────────────────────────────────────────────────

class NormalizationService:

    def from_github(self, profile: GitHubCandidateProfile) -> UnifiedCandidate:
        skills = _merge_skills(
            language_list=profile.language_list,
            topics=profile.all_topics,
            linkedin_skills=[],
        )

        projects = [
            NormalizedProject(
                name=repo.name,
                description=repo.description,
                url=repo.url,
                stars=repo.stars,
                forks=repo.forks,
                primary_language=repo.primary_language,
                topics=repo.topics,
            )
            for repo in profile.top_repos
        ]

        seniority = _infer_seniority(
            experience_years=None,
            current_role=profile.company,         # GitHub has no role, company is best proxy
            account_age_years=profile.account_age_years,
        )

        domain = _infer_domain(
            headline=None,
            about=profile.bio,
            bio=profile.bio,
            topics=profile.all_topics,
            experience=[],
        )

        candidate = UnifiedCandidate(
            name=profile.name or profile.username,
            location=profile.location,
            email=profile.email,
            github_url=profile.profile_url,
            portfolio_url=profile.blog if profile.blog else None,
            skills=skills,
            top_languages=profile.top_languages,
            current_company=profile.company,
            github_repos_count=profile.public_repos,
            total_stars_earned=profile.total_stars_earned,
            total_forks_earned=profile.total_forks_earned,
            top_projects=projects,
            active_days_last_month=profile.active_days_last_month,
            account_age_years=profile.account_age_years,
            seniority_inferred=seniority,
            domain_inferred=domain,
            open_to_work=profile.hireable or False,
            sources=["github"],
        )

        candidate.profile_completeness = _compute_completeness(candidate)
        return candidate

    def from_linkedin(self, profile: LinkedInProfile) -> UnifiedCandidate:
        skills = _merge_skills(
            language_list=[],
            topics=[],
            linkedin_skills=profile.skills,
        )

        experience = [
            NormalizedExperience(
                title=e.title if hasattr(e, "title") else e.get("title", ""),
                company=e.company if hasattr(e, "company") else e.get("company", ""),
                duration=e.duration if hasattr(e, "duration") else e.get("duration"),
                description=e.description if hasattr(e, "description") else e.get("description"),
            )
            for e in profile.experience
        ]

        education = [
            NormalizedEducation(
                degree=e.degree if hasattr(e, "degree") else e.get("degree"),
                institution=e.institution if hasattr(e, "institution") else e.get("institution", ""),
                year=e.year if hasattr(e, "year") else e.get("year"),
            )
            for e in profile.education
        ]

        seniority = _infer_seniority(
            experience_years=profile.total_experience_years,
            current_role=profile.current_role,
            account_age_years=None,
        )

        domain = _infer_domain(
            headline=profile.headline,
            about=profile.about,
            bio=None,
            topics=[],
            experience=experience,
        )

        candidate = UnifiedCandidate(
            name=profile.full_name,
            location=profile.location,
            email=profile.email,
            phone=profile.phone,
            linkedin_url=profile.profile_url,
            skills=skills,
            total_experience_years=profile.total_experience_years,
            current_role=profile.current_role,
            current_company=profile.current_company,
            experience=experience,
            education=education,
            certifications=profile.certifications,
            seniority_inferred=seniority,
            domain_inferred=domain,
            open_to_work=profile.open_to_work,
            sources=[profile.source],
        )

        candidate.profile_completeness = _compute_completeness(candidate)
        return candidate

    def normalize_github_list(
        self, profiles: list[GitHubCandidateProfile]
    ) -> list[UnifiedCandidate]:
        return [self.from_github(p) for p in profiles]

    def normalize_linkedin_list(
        self, profiles: list[LinkedInProfile]
    ) -> list[UnifiedCandidate]:
        return [self.from_linkedin(p) for p in profiles]

    def deduplicate(
        self, candidates: list[UnifiedCandidate]
    ) -> list[UnifiedCandidate]:
        """
        Deduplicates by email first, then name+location.
        When a duplicate is found, merges the two profiles —
        combined profile gets both sources and the best data from each.
        """
        seen_emails: dict[str, int] = {}       # email → index in result list
        seen_names: dict[str, int] = {}        # "name|location" → index
        result: list[UnifiedCandidate] = []

        for candidate in candidates:
            merged_into = None

            # Email match
            if candidate.email:
                key = candidate.email.lower().strip()
                if key in seen_emails:
                    merged_into = seen_emails[key]

            # Name + location match (fallback)
            if merged_into is None and candidate.name:
                loc = (candidate.location or "").lower().strip()
                name_key = f"{candidate.name.lower().strip()}|{loc}"
                if name_key in seen_names:
                    merged_into = seen_names[name_key]

            if merged_into is not None:
                # Merge this candidate into the existing one
                existing = result[merged_into]
                existing = self._merge(existing, candidate)
                result[merged_into] = existing
            else:
                idx = len(result)
                result.append(candidate)

                if candidate.email:
                    seen_emails[candidate.email.lower().strip()] = idx
                if candidate.name:
                    loc = (candidate.location or "").lower().strip()
                    seen_names[f"{candidate.name.lower().strip()}|{loc}"] = idx

        return result

    def _merge(self, base: UnifiedCandidate, other: UnifiedCandidate) -> UnifiedCandidate:
        """
        Merges two profiles representing the same person into one richer profile.
        GitHub fields fill technical gaps; LinkedIn fills career gaps.
        """
        # Merge skills
        merged_skills = _merge_skills(
            language_list=[s for s in other.skills if s not in base.skills],
            topics=[],
            linkedin_skills=base.skills,
        )

        # Prefer non-null values — take from whichever source has them
        base.skills                = merged_skills
        base.name                  = base.name or other.name
        base.location              = base.location or other.location
        base.email                 = base.email or other.email
        base.phone                 = base.phone or other.phone
        base.github_url            = base.github_url or other.github_url
        base.linkedin_url          = base.linkedin_url or other.linkedin_url
        base.portfolio_url         = base.portfolio_url or other.portfolio_url
        base.top_languages         = base.top_languages or other.top_languages
        base.total_experience_years = base.total_experience_years or other.total_experience_years
        base.current_role          = base.current_role or other.current_role
        base.current_company       = base.current_company or other.current_company
        base.experience            = base.experience or other.experience
        base.education             = base.education or other.education
        base.certifications        = base.certifications or other.certifications
        base.github_repos_count    = base.github_repos_count or other.github_repos_count
        base.total_stars_earned    = base.total_stars_earned or other.total_stars_earned
        base.top_projects          = base.top_projects or other.top_projects
        base.active_days_last_month = base.active_days_last_month or other.active_days_last_month
        base.account_age_years     = base.account_age_years or other.account_age_years
        base.seniority_inferred    = base.seniority_inferred or other.seniority_inferred
        base.domain_inferred       = base.domain_inferred or other.domain_inferred
        base.open_to_work          = base.open_to_work or other.open_to_work

        # Merge sources list
        for src in other.sources:
            if src not in base.sources:
                base.sources.append(src)

        # Recompute completeness — merged profile should score higher
        base.profile_completeness = _compute_completeness(base)

        return base


normalization_service = NormalizationService()
