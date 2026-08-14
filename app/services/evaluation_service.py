# Phase 6 Stage 2 — Ollama AI deep evaluation.
# Runs only on candidates who passed Stage 1 filter.

import json
import re
import time
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
Tools and Platforms: {tools_and_platforms}
Domain: {domain}

CANDIDATE PROFILE:
Name: {name}
Current Role: {current_role} at {current_company}
Experience: {experience_years} years | Seniority: {seniority_inferred}
Skills: {skills}
Top Languages: {top_languages}
Top Projects: {top_projects}
Certifications: {certifications}

Stage 1 Analysis:
- Skill Match: {skill_match_score} | Semantic Similarity: {semantic_similarity}
- Matched: {matched_skills}
- Missing: {missing_skills}

Return ONLY a JSON object. No markdown. No explanation.

{{
  "overall_fit_score": <integer 0-100>,
  "recommendation": "<Strong Match|Good Match|Partial Match|Not Recommended>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "justification": "<ONE sentence, max 30 words, explaining the overall fit>",
  "skill_gap_analysis": "<ONE sentence, max 25 words, on missing skills and criticality>"
}}

Scoring: 75-100 Strong Match | 50-74 Good Match | 30-49 Partial Match | 0-29 Not Recommended
Be concise and decisive. Do not restate the job requirements back."""


def _build_prompt(candidate: UnifiedCandidate, jd: JobDescription, stage1: dict) -> str:
    projects = [
        f"{p.name} ({p.stars}⭐)"
        for p in candidate.top_projects[:2]
    ]
    missing = [g.skill for g in stage1.get("skill_gaps", [])][:6]
    return EVALUATION_PROMPT.format(
        job_role=jd.job_role,
        seniority_level=jd.seniority_level or "not specified",
        required_skills=", ".join(jd.required_skills or []),
        nice_to_have_skills=", ".join(jd.nice_to_have_skills or []),
        experience_required=jd.experience_required or "not specified",
        tools_and_platforms=", ".join(jd.tools_and_platforms or []),
        domain=jd.domain or "not specified",
        name=candidate.name or "Unknown",
        current_role=candidate.current_role or "not provided",
        current_company=candidate.current_company or "not provided",
        experience_years=candidate.total_experience_years or "not provided",
        seniority_inferred=candidate.seniority_inferred or "unknown",
        skills=", ".join(candidate.skills[:10]),
        top_languages=str(dict(list(candidate.top_languages.items())[:3])),
        top_projects="; ".join(projects) if projects else "none",
        certifications=", ".join(candidate.certifications[:3]) if candidate.certifications else "none",
        skill_match_score=stage1.get("skill_match_score", 0),
        semantic_similarity=stage1.get("semantic_similarity", 0),
        matched_skills=", ".join(stage1.get("matched_skills", [])[:8]),
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


def _template_evaluation(stage1: dict) -> dict:
    """
    Fast, Ollama-free evaluation for candidates whose Stage-1 composite score
    is below settings.LLM_SCORE_THRESHOLD. Built directly from the rule-based
    skill match we already computed — no extra network call, no hallucination
    risk, and arguably more honest than an LLM paragraph restating the same
    skill gaps in prose (see conversation 2026-07-19 for the measured example).
    """
    composite = stage1.get("composite_score", 0)
    score = round(composite * 100)
    matched = stage1.get("matched_skills", [])
    gaps = [g.skill for g in stage1.get("skill_gaps", [])]

    if score >= 75:
        recommendation = "Strong Match"
    elif score >= 50:
        recommendation = "Good Match"
    elif score >= 30:
        recommendation = "Partial Match"
    else:
        recommendation = "Not Recommended"

    matched_preview = ", ".join(matched[:5]) + ("…" if len(matched) > 5 else "")
    gaps_preview = ", ".join(gaps[:5]) + ("…" if len(gaps) > 5 else "")

    justification = (
        f"Matches {len(matched)} of the required skills"
        + (f" ({matched_preview})" if matched else "")
        + f". Stage-1 composite score: {composite:.2f}."
    )
    skill_gap_analysis = (
        f"Missing: {gaps_preview}." if gaps else "No critical skill gaps identified."
    )

    return {
        "overall_fit_score": score,
        "recommendation": recommendation,
        "strengths": matched[:3],
        "justification": justification,
        "skill_gap_analysis": skill_gap_analysis,
    }


class EvaluationService:

    async def evaluate_candidate(
        self,
        candidate: UnifiedCandidate,
        jd: JobDescription,
        stage1: dict,
        use_llm: bool = True,
    ) -> CandidateEvaluation:
        if not use_llm:
            # Below LLM_SCORE_THRESHOLD — skip Ollama entirely (see _template_evaluation).
            data = _template_evaluation(stage1)
        else:
            prompt = _build_prompt(candidate, jd, stage1)
            prompt_chars = len(prompt)
            call_start = time.perf_counter()
            try:
                raw = await ollama_client.generate(prompt, temperature=0.2)
                data = json.loads(_clean_json(raw))
                elapsed = time.perf_counter() - call_start
                print(f"[TIMING]   Ollama eval — {candidate.name!r}: {elapsed:.2f}s "
                      f"(prompt={prompt_chars} chars, response={len(raw)} chars)")
            except Exception as e:
                elapsed = time.perf_counter() - call_start
                print(f"[TIMING]   Ollama eval — {candidate.name!r}: FAILED after {elapsed:.2f}s")
                print(f"[Evaluation] Ollama failed for {candidate.name}: {e}")
                data = _template_evaluation(stage1)

        score = float(data.get("overall_fit_score", 0))
        return CandidateEvaluation(
            name=candidate.name, location=candidate.location,
            email=candidate.email, github_url=candidate.github_url,
            linkedin_url=candidate.linkedin_url, portfolio_url=candidate.portfolio_url,
            sources=candidate.sources, skills=candidate.skills[:10],
            top_languages=candidate.top_languages,
            top_projects=[p.model_dump() for p in candidate.top_projects[:2]],
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
            resume_url=getattr(candidate, "resume_url", None),
        )

    async def evaluate_all(
        self,
        filtered: list[tuple[UnifiedCandidate, dict]],
        jd: JobDescription,
        max_evaluated: int = 5,
        llm_score_threshold: float = 0.35,
    ) -> list[CandidateEvaluation]:
        subset = filtered[:min(len(filtered), max_evaluated)]
        results = []
        llm_count = template_count = 0
        for candidate, stage1 in subset:
            use_llm = stage1.get("composite_score", 0) >= llm_score_threshold
            llm_count += use_llm
            template_count += not use_llm
            results.append(await self.evaluate_candidate(candidate, jd, stage1, use_llm=use_llm))
        print(f"[TIMING] Stage 2 breakdown: {llm_count} sent to Ollama, "
              f"{template_count} templated (composite < {llm_score_threshold}, no Ollama call)")
        results.sort(key=lambda x: x.overall_fit_score, reverse=True)
        return results


evaluation_service = EvaluationService()
