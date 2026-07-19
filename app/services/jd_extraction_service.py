import json
import re
from app.integrations.ollama_client import ollama_client
from app.schemas.jd_schema import ExtractedJDResponse


PROMPT_TEMPLATE = """You are an HR data extraction engine.

Extract fields from the job description below and return ONLY a JSON object.
No markdown. No explanation. No extra text.

JSON format:
{{
  "job_role": "string",
  "seniority_level": "junior|mid|senior|lead|null",
  "required_skills": ["string"],
  "nice_to_have_skills": ["string"],
  "experience_required": "string or null",
  "qualifications": ["string"],
  "employment_type": "full-time|part-time|contract|remote|hybrid|null",
  "domain": "string or null",
  "key_responsibilities": ["string"],
  "tools_and_platforms": ["string"],
  "location": "string or null"
}}

Rules:
- required_skills: only hard technical skills explicitly stated as required.
  Each array entry must be ONE atomic skill/technology name — if the JD lists
  several together ("HTML5, CSS3, JavaScript, TypeScript" or "React.js and
  Node.js"), split them into separate array entries, one per technology.
  Do NOT include lead-in phrases like "Proficiency in" or "Knowledge of" —
  extract just the skill name itself.
  Example: JD text "Proficiency in HTML5, CSS3, JavaScript, TypeScript" →
  required_skills entries: "HTML5", "CSS3", "JavaScript", "TypeScript"
  (four separate strings), NOT one combined string.
- nice_to_have_skills: skills marked as preferred/bonus/nice-to-have. Same
  atomic-entry rule as required_skills.
- tools_and_platforms: infrastructure/DevOps/PM tools (Docker, AWS, Jira,
  etc.). Same atomic-entry rule.
- domain: industry domain if mentioned (fintech, healthtech, ecommerce, etc.)
- location: city/country/remote if stated; null otherwise
- All list fields default to [] if nothing found
- Null fields use null, not empty string

Job Description:
{job_description}"""


class JDExtractionService:

    def _clean_json(self, raw: str) -> str:
        """Strip markdown fences and extract the first JSON object."""
        raw = re.sub(r"```json|```", "", raw).strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return match.group(0) if match else raw

    async def extract(self, job_description: str) -> ExtractedJDResponse:
        prompt = PROMPT_TEMPLATE.format(job_description=job_description)
        raw = await ollama_client.generate(prompt, temperature=0.1)
        cleaned = self._clean_json(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(f"LLM returned unparseable JSON: {cleaned[:300]}")

        # Ensure all list fields are actually lists (small model can return null)
        list_fields = [
            "required_skills", "nice_to_have_skills", "qualifications",
            "key_responsibilities", "tools_and_platforms",
        ]
        for field in list_fields:
            if not isinstance(data.get(field), list):
                data[field] = []

        return ExtractedJDResponse(**data)


jd_extraction_service = JDExtractionService()
