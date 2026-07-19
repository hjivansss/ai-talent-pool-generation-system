# Phase 6 Stage 1 — Rule-based skill matching with optional semantic boost.
# Pure Python. Falls back gracefully if embeddings unavailable.

import re
from app.schemas.unified_candidate import UnifiedCandidate
from app.models.job_description import JobDescription
from app.schemas.talent_pool_schema import SkillGap
from app.services.skill_utils import flatten_skill_phrases


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
    """
    Checks whether candidate skill `c` matches JD requirement phrase `j`.
    Requirement phrases are often full sentences ("Proficiency in SQL",
    "AWS or Azure"), so this needs to find `c` as a whole word inside `j`
    (or vice versa), not just compare them directly.

    2026-07-19 fix: the previous version used `len(x) > 3 and x in y` as a
    substring check, which silently excluded every skill 3 characters or
    shorter — SQL, AWS, Git, R, Go, C# — from ever matching a JD phrase that
    mentions them, since e.g. len("sql") == 3 fails `> 3`. That was the root
    cause of near-uniform ~0.11 skill_match_score across candidates regardless
    of actual fit. Word-boundary regex matching works correctly at any length
    and additionally avoids false positives a raw substring check would allow
    at longer lengths too (e.g. "go" inside "algorithm", "r" inside "docker").
    """
    cn, jn = _normalize(c), _normalize(j)
    if cn == jn:
        return True
    for canonical, variants in ALIASES.items():
        group = [canonical] + [_normalize(v) for v in variants]
        if cn in group and jn in group:
            return True
    if re.search(rf"\b{re.escape(cn)}\b", jn):
        return True
    if re.search(rf"\b{re.escape(jn)}\b", cn):
        return True
    return False


class MatchingService:

    def score(
        self,
        candidate: UnifiedCandidate,
        jd: JobDescription,
        semantic_similarity: float = 0.0,
        has_semantic: bool = False,
    ) -> dict:
        """
        Computes composite Stage 1 score.
        semantic_similarity (0.0-1.0) is passed in from embedding service when available
        (LinkedIn/resume candidates only — GitHub has no embedding).

        Base weights (when semantic is available): skills 55%, experience 20%,
        tools 10%, semantic 15%. When semantic is unavailable (has_semantic=False,
        e.g. GitHub candidates, or embedding failed), the semantic slice is
        proportionally redistributed across the other three so the *ratios*
        between skills/experience/tools stay identical either way — a GitHub
        candidate and a LinkedIn candidate with the same skills/experience/tools
        profile now get the same composite score. Previously GitHub silently used
        a different hand-tuned weight set (60/25/15) than the redistributed
        version of 55/20/10 would give (~64.7/23.5/11.8), which meant otherwise
        identical candidates scored differently purely based on source.
        """
        # Flatten any bundled skill phrases (see skill_utils.py) so
        # skill_match_score reflects real atomic requirements — a JD with
        # "Proficiency in HTML5, CSS3, JavaScript, TypeScript" as one entry
        # was previously counted as a single requirement instead of four.
        required_skills     = flatten_skill_phrases(jd.required_skills or [])
        tools_and_platforms = flatten_skill_phrases(jd.tools_and_platforms or [])
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

        SKILL_W, EXP_W, TOOLS_W, SEMANTIC_W = 0.55, 0.20, 0.10, 0.15
        if has_semantic:
            composite = (
                skill_match_score      * SKILL_W +
                experience_match_score * EXP_W +
                tools_match_score      * TOOLS_W +
                semantic_similarity    * SEMANTIC_W
            )
        else:
            # Redistribute the semantic slice proportionally across the rest
            # instead of a separate hand-tuned weight set.
            rescale = 1.0 / (SKILL_W + EXP_W + TOOLS_W)
            composite = (
                skill_match_score      * SKILL_W * rescale +
                experience_match_score * EXP_W   * rescale +
                tools_match_score      * TOOLS_W * rescale
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
            (c, self.score(
                c, jd,
                semantic_similarity=similarity_map.get(c.name or "", 0.0),
                has_semantic=(c.name or "") in similarity_map,
            ))
            for c in candidates
        ]
        passed = [(c, s) for c, s in scored if s["composite_score"] >= min_score]
        if len(passed) < 3:
            passed = [(c, s) for c, s in scored if s["composite_score"] >= 0.1]
        passed.sort(key=lambda x: x[1]["composite_score"], reverse=True)
        return passed


matching_service = MatchingService()


