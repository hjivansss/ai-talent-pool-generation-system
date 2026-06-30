import io
import json
import re
from app.integrations.ollama_client import ollama_client
from app.schemas.candidate_schema import LinkedInProfile, LinkedInExperience, LinkedInEducation


RESUME_PROMPT = """You are a resume parser.
Extract structured information from this resume text and return ONLY a JSON object.
No markdown. No explanation. No extra text.

{{
  "full_name": "string",
  "email": "string or null",
  "phone": "string or null",
  "location": "string or null",
  "skills": ["string"],
  "experience": [
    {{"title": "string", "company": "string",
     "duration": "string or null", "description": "string or null"}}
  ],
  "education": [
    {{"degree": "string or null", "institution": "string", "year": "string or null"}}
  ],
  "certifications": ["string"],
  "total_experience_years": <number or null>,
  "current_role": "string or null",
  "current_company": "string or null"
}}

Rules:
- skills: flat list of all technical and domain skills mentioned
- total_experience_years: calculate from experience durations if possible
- current_role: most recent job title
- current_company: most recent employer
- All list fields default to [] if nothing found
- Null fields use null not empty string

Resume text:
{resume_text}"""


class ResumeParser:

    def _extract_text_pdf(self, file_bytes: bytes) -> str:
        """Extract text from a PDF file using pdfplumber."""
        import pdfplumber

        pages_text = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

        full_text = "\n".join(pages_text).strip()
        if not full_text:
            raise ValueError(
                "No text could be extracted from this PDF. "
                "It appears to be a scanned image. "
                "Please upload a text-based PDF."
            )
        return full_text

    def _extract_text_docx(self, file_bytes: bytes) -> str:
        """Extract text from a DOCX file using python-docx."""
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs)

    def _clean_json(self, raw: str) -> str:
        """Strip markdown fences and extract the first JSON object."""
        raw = re.sub(r"```json|```", "", raw).strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return match.group(0) if match else raw

    async def parse(self, file_bytes: bytes, filename: str) -> LinkedInProfile:
        """
        Parse a PDF or DOCX resume into a LinkedInProfile.

        Steps:
        1. Detect file type from extension.
        2. Extract raw text.
        3. Call Ollama to get structured JSON.
        4. Guard list fields and map to LinkedInProfile.
        """
        lower = filename.lower()
        if lower.endswith(".pdf"):
            text = self._extract_text_pdf(file_bytes)
        elif lower.endswith(".docx") or lower.endswith(".doc"):
            text = self._extract_text_docx(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {filename}. Only PDF and DOCX are accepted.")

        if not text.strip():
            raise ValueError("Resume appears to be empty — no text could be extracted.")

        prompt = RESUME_PROMPT.format(resume_text=text)
        raw = await ollama_client.generate(prompt, temperature=0.1)
        cleaned = self._clean_json(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(f"LLM returned unparseable JSON: {cleaned[:300]}")

        # Guard list fields — small models can return null instead of []
        list_fields = ["skills", "experience", "education", "certifications"]
        for field in list_fields:
            if not isinstance(data.get(field), list):
                data[field] = []

        # Map experience dicts → LinkedInExperience objects
        experience = []
        for exp in data.get("experience", []):
            if isinstance(exp, dict) and exp.get("company"):
                experience.append(
                    LinkedInExperience(
                        title=exp.get("title", "Unknown"),
                        company=exp.get("company", "Unknown"),
                        duration=exp.get("duration"),
                        description=exp.get("description"),
                    )
                )

        # Map education dicts → LinkedInEducation objects
        education = []
        for edu in data.get("education", []):
            if isinstance(edu, dict) and edu.get("institution"):
                education.append(
                    LinkedInEducation(
                        degree=edu.get("degree"),
                        institution=edu.get("institution", "Unknown"),
                        year=edu.get("year"),
                    )
                )

        return LinkedInProfile(
            full_name=data.get("full_name") or "Unknown",
            email=data.get("email"),
            phone=data.get("phone"),
            location=data.get("location"),
            skills=data.get("skills", []),
            experience=experience,
            education=education,
            certifications=data.get("certifications", []),
            total_experience_years=data.get("total_experience_years"),
            current_role=data.get("current_role"),
            current_company=data.get("current_company"),
            open_to_work=False,
            source="resume",
        )


resume_parser = ResumeParser()
