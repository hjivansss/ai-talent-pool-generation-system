# Phase 6 Stage 2 — Ollama AI deep evaluation.
# Runs only on candidates who passed Stage 1 filter.
# Produces per-candidate fit score, justification, strengths, skill gap analysis.

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
Current Role: {current_role}
Current Company: {current_company}
Experience Years: {experience_years}
Seniority: {seniority_inferred}
Skills: {skills}
Top Languages (bytes written): {top_languages}
Top Projects: {top_projects}
Active Days Last Month: {active_days}
Account Age Years: {account_age}
Certifications: {certifications}
Sources: {sources}

Stage 1 Scores:
- Skill Match: {skill_match_score}
- Experience Match: {experience_match_score}
- Matched Skills: {matched_skills}
- Missing Skills: {missing_skills}

Evaluate this candidate and return ONLY a JSON object. No markdown. No explanation.

{{
  "overall_fit_score": <integer 0-100>,
  "recommendation": "<Strong Match|Good Match|Partial Match|Not Recommended>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "justification": "<2-3 sentence paragraph explaining the overall fit>",
  "skill_gap_analysis": "<1-2 sentences on missing skills and how critical they are>"
}}

Scoring guide:
- 75-100: Strong Match — meets most requirements, minor gaps only
- 50-74:  Good Match — meets core requirements, some gaps
- 30-49:  Partial Match — meets some requirements, significant gaps
- 0-29:   Not Recommended — does not meet minimum requirements

IMPORTANT: You MUST give different scores to different candidates.
Do NOT give everyone 50. Aniket has mobile projects — score him higher.
Rahul is a backend developer for a mobile role — score him lower.
Be decisive. Use the full 0-100 range.

Be specific. Reference actual skills, projects, and experience years in your response."""


def _build_prompt(
    candidate: UnifiedCandidate,
    jd: JobDescription,
    stage1_scores: dict,
) -> str:
    top_projects = []
    for p in candidate.top_projects[:3]:
        top_projects.append(f"{p.name} ({p.stars}⭐) — {p.description or 'no description'}")

    missing_skills = [g.skill for g in stage1_scores.get("skill_gaps", [])]

    return EVALUATION_PROMPT.format(
        job_role            = jd.job_role,
        seniority_level     = jd.seniority_level or "not specified",
        required_skills     = ", ".join(jd.required_skills or []),
        nice_to_have_skills = ", ".join(jd.nice_to_have_skills or []),
        experience_required = jd.experience_required or "not specified",
        key_responsibilities= "; ".join((jd.key_responsibilities or [])[:3]),
        tools_and_platforms = ", ".join(jd.tools_and_platforms or []),
        domain              = jd.domain or "not specified",
        name                = candidate.name or "Unknown",
        current_role        = candidate.current_role or "not provided",
        current_company     = candidate.current_company or "not provided",
        experience_years    = candidate.total_experience_years or "not provided",
        seniority_inferred  = candidate.seniority_inferred or "unknown",
        skills              = ", ".join(candidate.skills[:20]),
        top_languages       = str(dict(list(candidate.top_languages.items())[:5])),
        top_projects        = "; ".join(top_projects) if top_projects else "none",
        active_days         = candidate.active_days_last_month,
        account_age         = candidate.account_age_years,
        certifications      = ", ".join(candidate.certifications) if candidate.certifications else "none",
        sources             = ", ".join(candidate.sources),
        skill_match_score   = stage1_scores.get("skill_match_score", 0),
        experience_match_score = stage1_scores.get("experience_match_score", 0),
        matched_skills      = ", ".join(stage1_scores.get("matched_skills", [])),
        missing_skills      = ", ".join(missing_skills) if missing_skills else "none",
    )


def _clean_json(raw: str) -> str:
    raw = re.sub(r"```json|```", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return match.group(0) if match else raw


def _assign_tier(score: float) -> int:
    if score >= 75:
        return 1
    elif score >= 50:
        return 2
    return 3


class EvaluationService:

    async def evaluate_candidate(
        self,
        candidate: UnifiedCandidate,
        jd: JobDescription,
        stage1_scores: dict,
    ) -> CandidateEvaluation:
        """
        Runs Ollama evaluation for one candidate.
        Falls back to Stage 1 scores if Ollama fails.
        """
        prompt = _build_prompt(candidate, jd, stage1_scores)

        try:
            raw = await ollama_client.generate(prompt, temperature=0.2)
            cleaned = _clean_json(raw)
            data = json.loads(cleaned)
        except Exception as e:
            print(f"[Evaluation] Ollama failed for {candidate.name}: {e}")
            # Graceful fallback — use Stage 1 composite score * 100
            composite = stage1_scores.get("composite_score", 0)
            data = {
                "overall_fit_score": round(composite * 100),
                "recommendation":    "Partial Match",
                "strengths":         [],
                "justification":     "AI evaluation unavailable. Score based on skill matching only.",
                "skill_gap_analysis": "Unable to generate analysis.",
            }

        overall_score = float(data.get("overall_fit_score", 0))
        tier = _assign_tier(overall_score)

        return CandidateEvaluation(
            # Identity
            name               = candidate.name,
            location           = candidate.location,
            email              = candidate.email,
            github_url         = candidate.github_url,
            linkedin_url       = candidate.linkedin_url,
            portfolio_url      = candidate.portfolio_url,
            sources            = candidate.sources,

            # Skills snapshot
            skills             = candidate.skills[:20],
            top_languages      = candidate.top_languages,
            top_projects       = [p.model_dump() for p in candidate.top_projects[:3]],

            # Experience snapshot
            current_role       = candidate.current_role,
            current_company    = candidate.current_company,
            total_experience_years = candidate.total_experience_years,
            seniority_inferred = candidate.seniority_inferred,

            # Stage 1
            skill_match_score      = stage1_scores.get("skill_match_score", 0),
            experience_match_score = stage1_scores.get("experience_match_score", 0),
            tools_match_score      = stage1_scores.get("tools_match_score", 0),
            matched_skills         = stage1_scores.get("matched_skills", []),
            skill_gaps             = stage1_scores.get("skill_gaps", []),

            # Stage 2
            overall_fit_score  = overall_score,
            recommendation     = data.get("recommendation", "Partial Match"),
            tier               = tier,
            strengths          = data.get("strengths", []),
            justification      = data.get("justification", ""),
            skill_gap_analysis = data.get("skill_gap_analysis", ""),

            # Quality
            profile_completeness = candidate.profile_completeness,
            open_to_work         = candidate.open_to_work,
        )

    async def evaluate_all(
        self,
        filtered_candidates: list[tuple[UnifiedCandidate, dict]],
        jd: JobDescription,
        max_evaluated: int = 15,
    ) -> list[CandidateEvaluation]:
        """
        Evaluates all filtered candidates sequentially (not concurrent —
        Ollama is single-threaded locally).
        Caps at max_evaluated to control response time.
        Sorts final list by overall_fit_score descending.
        """
        results: list[CandidateEvaluation] = []
        cap = min(len(filtered_candidates), max_evaluated)

        for candidate, stage1_scores in filtered_candidates[:cap]:
            evaluated = await self.evaluate_candidate(candidate, jd, stage1_scores)
            results.append(evaluated)

        # Sort by overall fit score descending
        results.sort(key=lambda x: x.overall_fit_score, reverse=True)
        return results


evaluation_service = EvaluationService()
