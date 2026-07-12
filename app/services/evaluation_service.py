# Phase 6 Stage 2 — Ollama AI deep evaluation.
# Runs only on candidates who passed Stage 1 filter.

import json
import re
from app.integrations.ollama_client import ollama_client
from app.schemas.unified_candidate import UnifiedCandidate
from app.models.job_description import JobDescription
from app.schemas.talent_pool_schema import CandidateEvaluation, SkillGap


EVALUATION_PROMPT = """You are a senior technical recruiter evaluating a candidate for a job role.

JOB REQUIREMENTS:
Role: {job_role}
Seniority: {seniority_level}
Required Skills: {required_skills}
Nice to Have: {nice_to_have_skills}
Experience Required: {experience_required}
Key Responsibilities: {key_responsibilities}
Tools and Platforms: {tools_and_platforms}
Domain: {domain}

CANDIDATE PROFILE:
Name: {name}
Current Role: {current_role} at {current_company}
Experience: {experience_years} years | Seniority: {seniority_inferred}
Skills: {skills}
Top Languages (bytes written): {top_languages}
Top Projects: {top_projects}
Active Days Last Month: {active_days}
Certifications: {certifications}
Sources: {sources}

Stage 1 Analysis:
- Skill Match: {skill_match_score} | Semantic Similarity: {semantic_similarity}
- Matched: {matched_skills}
- Missing: {missing_skills}

Return ONLY a JSON object. No markdown. No explanation.

{{
  "overall_fit_score": <integer 0-100>,
  "recommendation": "<Strong Match|Good Match|Partial Match|Not Recommended>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "justification": "<2-3 sentence paragraph explaining the overall fit>",
  "skill_gap_analysis": "<1-2 sentences on missing skills and criticality>"
}}

Scoring: 75-100 Strong Match | 50-74 Good Match | 30-49 Partial Match | 0-29 Not Recommended
Use the full 0-100 range. Give different scores to different candidates. Be decisive and specific."""


def _build_prompt(candidate: UnifiedCandidate, jd: JobDescription, stage1: dict) -> str:
    projects = [
        f"{p.name} ({p.stars}⭐) — {p.description or 'no description'}"
        for p in candidate.top_projects[:3]
    ]
    missing = [g.skill for g in stage1.get("skill_gaps", [])]
    return EVALUATION_PROMPT.format(
        job_role=jd.job_role,
        seniority_level=jd.seniority_level or "not specified",
        required_skills=", ".join(jd.required_skills or []),
        nice_to_have_skills=", ".join(jd.nice_to_have_skills or []),
        experience_required=jd.experience_required or "not specified",
        key_responsibilities="; ".join((jd.key_responsibilities or [])[:2]),
        tools_and_platforms=", ".join(jd.tools_and_platforms or []),
        domain=jd.domain or "not specified",
        name=candidate.name or "Unknown",
        current_role=candidate.current_role or "not provided",
        current_company=candidate.current_company or "not provided",
        experience_years=candidate.total_experience_years or "not provided",
        seniority_inferred=candidate.seniority_inferred or "unknown",
        skills=", ".join(candidate.skills[:15]),
        top_languages=str(dict(list(candidate.top_languages.items())[:5])),
        top_projects="; ".join(projects) if projects else "none",
        active_days=candidate.active_days_last_month,
        certifications=", ".join(candidate.certifications) if candidate.certifications else "none",
        sources=", ".join(candidate.sources),
        skill_match_score=stage1.get("skill_match_score", 0),
        semantic_similarity=stage1.get("semantic_similarity", 0),
        matched_skills=", ".join(stage1.get("matched_skills", [])),
        missing_skills=", ".join(missing) if missing else "none",
    )


def _clean_json(raw: str) -> str:
    raw = re.sub(r"```json|```", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return match.group(0) if match else raw


def _assign_tier(score: float) -> int:
    if score >= 75: return 1
    if score >= 50: return 2
    return 3


class EvaluationService:

    async def evaluate_candidate(
        self,
        candidate: UnifiedCandidate,
        jd: JobDescription,
        stage1: dict,
    ) -> CandidateEvaluation:
        prompt = _build_prompt(candidate, jd, stage1)
        try:
            raw = await ollama_client.generate(prompt, temperature=0.2)
            data = json.loads(_clean_json(raw))
        except Exception as e:
            print(f"[Evaluation] Ollama failed for {candidate.name}: {e}")
            composite = stage1.get("composite_score", 0)
            data = {
                "overall_fit_score": round(composite * 100),
                "recommendation": "Partial Match",
                "strengths": [],
                "justification": "AI evaluation unavailable. Score based on skill matching only.",
                "skill_gap_analysis": "Unable to generate analysis.",
            }

        score = float(data.get("overall_fit_score", 0))
        return CandidateEvaluation(
            name=candidate.name, location=candidate.location,
            email=candidate.email, github_url=candidate.github_url,
            linkedin_url=candidate.linkedin_url, portfolio_url=candidate.portfolio_url,
            sources=candidate.sources, skills=candidate.skills[:15],
            top_languages=candidate.top_languages,
            top_projects=[p.model_dump() for p in candidate.top_projects[:3]],
            current_role=candidate.current_role, current_company=candidate.current_company,
            total_experience_years=candidate.total_experience_years,
            seniority_inferred=candidate.seniority_inferred,
            skill_match_score=stage1.get("skill_match_score", 0),
            experience_match_score=stage1.get("experience_match_score", 0),
            tools_match_score=stage1.get("tools_match_score", 0),
            semantic_similarity=stage1.get("semantic_similarity", 0.0),
            matched_skills=stage1.get("matched_skills", []),
            skill_gaps=stage1.get("skill_gaps", []),
            overall_fit_score=score, recommendation=data.get("recommendation", "Partial Match"),
            tier=_assign_tier(score), strengths=data.get("strengths", []),
            justification=data.get("justification", ""),
            skill_gap_analysis=data.get("skill_gap_analysis", ""),
            profile_completeness=candidate.profile_completeness,
            open_to_work=candidate.open_to_work,
        )

    async def evaluate_all(
        self,
        filtered: list[tuple[UnifiedCandidate, dict]],
        jd: JobDescription,
        max_evaluated: int = 5,
    ) -> list[CandidateEvaluation]:
        results = []
        for candidate, stage1 in filtered[:min(len(filtered), max_evaluated)]:
            results.append(await self.evaluate_candidate(candidate, jd, stage1))
        results.sort(key=lambda x: x.overall_fit_score, reverse=True)
        return results


evaluation_service = EvaluationService()
