# Phase 6 Stage 1 — Rule-based skill matching with optional semantic boost.
# Pure Python. Falls back gracefully if embeddings unavailable.

import re
from app.schemas.unified_candidate import UnifiedCandidate
from app.models.job_description import JobDescription
from app.schemas.talent_pool_schema import SkillGap


def _parse_experience_years(text: str | None) -> tuple[float, float]:
    if not text:
        return (0.0, 99.0)
    numbers = re.findall(r"\d+\.?\d*", text.lower())
    if not numbers:
        return (0.0, 99.0)
    if len(numbers) == 1:
        n = float(numbers[0])
        return (n, 99.0) if "+" in text else (max(0.0, n - 1), n + 2)
    return (float(numbers[0]), float(numbers[1]))


def _normalize(skill: str) -> str:
    return skill.lower().strip().replace("-", " ").replace("_", " ")


ALIASES: dict[str, list[str]] = {
    "node.js":    ["nodejs", "node js", "node"],
    "postgresql": ["postgres", "psql", "pg"],
    "javascript": ["js", "es6", "vanilla js"],
    "typescript": ["ts"],
    "python":     ["python3", "py"],
    "kubernetes": ["k8s", "kube"],
    "mongodb":    ["mongo", "mongoose"],
    "react":      ["reactjs", "react.js", "react native"],
    "fastapi":    ["fast api"],
    "docker":     ["containerization", "containers"],
    "aws":        ["amazon web services"],
    "rest api":   ["restful api", "rest", "api development", "api design"],
    "ci/cd":      ["cicd", "continuous integration", "devops pipeline"],
    "git":        ["github", "gitlab", "version control", "source control"],
    "linux":      ["unix", "bash", "shell scripting"],
    "flutter":    ["dart", "flutter sdk"],
}


def _skills_match(c: str, j: str) -> bool:
    cn, jn = _normalize(c), _normalize(j)
    if cn == jn:
        return True
    for canonical, variants in ALIASES.items():
        group = [canonical] + [_normalize(v) for v in variants]
        if cn in group and jn in group:
            return True
    if len(jn) > 3 and jn in cn:
        return True
    if len(cn) > 3 and cn in jn:
        return True
    return False


class MatchingService:

    def score(
        self,
        candidate: UnifiedCandidate,
        jd: JobDescription,
        semantic_similarity: float = 0.0,
    ) -> dict:
        """
        Computes composite Stage 1 score.
        semantic_similarity (0.0–1.0) is passed in from embedding service when available.
        Weights: skills 55%, experience 20%, tools 10%, semantic 15%.
        Falls back to skills 60%, experience 25%, tools 15% when no embedding.
        """
        required_skills     = jd.required_skills or []
        tools_and_platforms = jd.tools_and_platforms or []
        candidate_skills    = candidate.skills

        matched_skills, skill_gaps = [], []
        for req in required_skills:
            if any(_skills_match(c, req) for c in candidate_skills):
                matched_skills.append(req)
            else:
                skill_gaps.append(SkillGap(skill=req, criticality="critical"))

        skill_match_score = len(matched_skills) / len(required_skills) if required_skills else 0.5

        matched_tools = sum(
            1 for tool in tools_and_platforms
            if any(_skills_match(c, tool) for c in candidate_skills)
        )
        tools_match_score = matched_tools / len(tools_and_platforms) if tools_and_platforms else 0.5

        min_exp, max_exp = _parse_experience_years(jd.experience_required)
        yrs = candidate.total_experience_years
        if yrs is None:
            experience_match_score = 0.5
        elif min_exp <= yrs <= max_exp:
            experience_match_score = 1.0
        elif yrs < min_exp:
            experience_match_score = max(0.0, 1.0 - ((min_exp - yrs) / max(min_exp, 1)))
        else:
            experience_match_score = 0.8

        if semantic_similarity > 0:
            composite = (
                skill_match_score      * 0.55 +
                experience_match_score * 0.20 +
                tools_match_score      * 0.10 +
                semantic_similarity    * 0.15
            )
        else:
            composite = (
                skill_match_score      * 0.60 +
                experience_match_score * 0.25 +
                tools_match_score      * 0.15
            )

        return {
            "skill_match_score":      round(skill_match_score, 2),
            "experience_match_score": round(experience_match_score, 2),
            "tools_match_score":      round(tools_match_score, 2),
            "semantic_similarity":    round(semantic_similarity, 2),
            "composite_score":        round(composite, 2),
            "matched_skills":         matched_skills,
            "skill_gaps":             skill_gaps,
            "seniority_match": (
                candidate.seniority_inferred == jd.seniority_level
                if jd.seniority_level and candidate.seniority_inferred else True
            ),
        }

    def filter_candidates(
        self,
        candidates: list[UnifiedCandidate],
        jd: JobDescription,
        min_score: float = 0.2,
        similarity_map: dict[str, float] | None = None,
    ) -> list[tuple[UnifiedCandidate, dict]]:
        """
        Scores all candidates. similarity_map: {candidate.name → similarity_score}.
        Auto-lowers threshold to 0.1 if fewer than 3 pass.
        """
        similarity_map = similarity_map or {}
        scored = [
            (c, self.score(c, jd, similarity_map.get(c.name or "", 0.0)))
            for c in candidates
        ]
        passed = [(c, s) for c, s in scored if s["composite_score"] >= min_score]
        if len(passed) < 3:
            passed = [(c, s) for c, s in scored if s["composite_score"] >= 0.1]
        passed.sort(key=lambda x: x[1]["composite_score"], reverse=True)
        return passed


matching_service = MatchingService()

