import json

from app.integrations.ollama_client import ollama_client
from app.schemas.jd_schema import ExtractedJDResponse


class JDExtractionService:
    async def extract(self, job_description: str) -> ExtractedJDResponse:
        prompt = f"""
You are an expert HR job description parser.

Extract the following fields from the job description:
1. job_role
2. required_skills
3. experience_required
4. qualifications

Return ONLY valid JSON.
Do not include markdown.
Do not include explanation.

JSON format:
{{
  "job_role": "string",
  "required_skills": ["string"],
  "experience_required": "string",
  "qualifications": ["string"]
}}

Job Description:
{job_description}
"""

        llm_response = await ollama_client.generate(prompt)

        try:
            parsed_data = json.loads(llm_response)
        except json.JSONDecodeError:
            raise ValueError(f"Ollama returned invalid JSON: {llm_response}")

        return ExtractedJDResponse(**parsed_data)


jd_extraction_service = JDExtractionService()