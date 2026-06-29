# Phase 6 Stage 1 — Rule-based skill matching.
# Fast, pure Python, no AI.
# Runs on ALL candidates before Ollama evaluation.
# Filters out poor matches, computes skill gaps, produces initial scores.

import re
from app.schemas.unified_candidate import UnifiedCandidate
from app.models.job_description import JobDescription
from app.schemas.talent_pool_schema import SkillGap


# ── Experience parsing ──────────────────────────────────────────────────────────

def _parse_experience_years(experience_str: str | None) -> tuple[float, float]:
    """
    Parses JD experience string like '3+ years', '2-5 years', '5 years'
    into (min_years, max_years).
    """
    if not experience_str:
        return (0.0, 99.0)

    text = experience_str.lower()
    numbers = re.findall(r"\d+\.?\d*", text)

    if not numbers:
        return (0.0, 99.0)

    if len(numbers) == 1:
        n = float(numbers[0])
        # "3+ years" means minimum 3
        if "+" in text:
            return (n, 99.0)
        return (max(0.0, n - 1), n + 2)

    return (float(numbers[0]), float(numbers[1]))


# ── Skill normalization ─────────────────────────────────────────────────────────

def _normalize_skill(skill: str) -> str:
    return skill.lower().strip().replace("-", " ").replace("_", " ")


def _skills_match(candidate_skill: str, jd_skill: str) -> bool:
    """
    Fuzzy skill match — handles common variations.
    e.g. "nodejs" matches "node.js", "postgresql" matches "postgres"
    """
    c = _normalize_skill(candidate_skill)
    j = _normalize_skill(jd_skill)

    if c == j:
        return True

    # Common aliases
    aliases = {
        "node.js": ["nodejs", "node js", "node"],
        "postgresql": ["postgres", "psql"],
        "javascript": ["js"],
        "typescript": ["ts"],
        "python": ["python3", "py"],
        "kubernetes": ["k8s"],
        "elasticsearch": ["elastic", "es"],
        "mongodb": ["mongo"],
        "react": ["reactjs", "react.js"],
        "fastapi": ["fast api"],
    }

    for canonical, variants in aliases.items():
        group = [canonical] + variants
        if c in group and j in group:
            return True

    # Substring match for compound skills
    if len(j) > 3 and j in c:
        return True
    if len(c) > 3 and c in j:
        return True

    return False


# ── Main matching service ───────────────────────────────────────────────────────

class MatchingService:

    def score(
        self,
        candidate: UnifiedCandidate,
        jd: JobDescription,
    ) -> dict:
        """
        Computes Stage 1 rule-based scores for one candidate against a JD.
        Returns a dict with all scores and skill gap details.
        """
        required_skills   = jd.required_skills or []
        tools_and_platforms = jd.tools_and_platforms or []

        candidate_skills = candidate.skills

        # ── Skill match ─────────────────────────────────────────────────────────
        matched_skills: list[str] = []
        skill_gaps: list[SkillGap] = []

        for req_skill in required_skills:
            matched = any(
                _skills_match(c_skill, req_skill)
                for c_skill in candidate_skills
            )
            if matched:
                matched_skills.append(req_skill)
            else:
                skill_gaps.append(SkillGap(
                    skill=req_skill,
                    criticality="critical",
                ))

        skill_match_score = (
            len(matched_skills) / len(required_skills)
            if required_skills else 0.5
        )

        # ── Tools match ─────────────────────────────────────────────────────────
        matched_tools = sum(
            1 for tool in tools_and_platforms
            if any(_skills_match(c_skill, tool) for c_skill in candidate_skills)
        )
        tools_match_score = (
            matched_tools / len(tools_and_platforms)
            if tools_and_platforms else 0.5
        )

        # ── Experience match ─────────────────────────────────────────────────────
        min_exp, max_exp = _parse_experience_years(jd.experience_required)
        candidate_years  = candidate.total_experience_years

        if candidate_years is None:
            # GitHub-only candidate — no experience data
            # Give neutral score rather than penalising
            experience_match_score = 0.5
        elif min_exp <= candidate_years <= max_exp:
            experience_match_score = 1.0
        elif candidate_years < min_exp:
            gap = min_exp - candidate_years
            experience_match_score = max(0.0, 1.0 - (gap / max(min_exp, 1)))
        else:
            # Over-experienced — slight penalty, not disqualifying
            experience_match_score = 0.8

        # ── Seniority match ──────────────────────────────────────────────────────
        seniority_match = (
            candidate.seniority_inferred == jd.seniority_level
            if jd.seniority_level and candidate.seniority_inferred
            else True   # no penalty if either side is unknown
        )

        # ── Composite Stage 1 score ──────────────────────────────────────────────
        # Weighted: skills matter most, then experience, then tools
        composite = (
            skill_match_score      * 0.60 +
            experience_match_score * 0.25 +
            tools_match_score      * 0.15
        )

        return {
            "skill_match_score":      round(skill_match_score, 2),
            "experience_match_score": round(experience_match_score, 2),
            "tools_match_score":      round(tools_match_score, 2),
            "composite_score":        round(composite, 2),
            "matched_skills":         matched_skills,
            "skill_gaps":             skill_gaps,
            "seniority_match":        seniority_match,
        }

    def filter_candidates(
        self,
        candidates: list[UnifiedCandidate],
        jd: JobDescription,
        min_score: float = 0.3,
    ) -> list[tuple[UnifiedCandidate, dict]]:
        """
        Scores all candidates and returns only those above min_score threshold.
        Returns list of (candidate, scores_dict) tuples sorted by composite score desc.
        If fewer than 3 pass the threshold, automatically lowers it to 0.15
        to avoid returning an empty pool.
        """
        scored = []
        for candidate in candidates:
            scores = self.score(candidate, jd)
            scored.append((candidate, scores))

        # Apply threshold
        passed = [(c, s) for c, s in scored if s["composite_score"] >= min_score]

        # Auto-lower threshold if too few passed
        if len(passed) < 3:
            passed = [(c, s) for c, s in scored if s["composite_score"] >= 0.15]

        # Sort by composite score descending
        passed.sort(key=lambda x: x[1]["composite_score"], reverse=True)

        return passed


matching_service = MatchingService()
