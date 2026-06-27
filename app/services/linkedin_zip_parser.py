# Parses a LinkedIn data export ZIP file into a LinkedInProfile object.
# LinkedIn export contains multiple CSVs — we use:
#   Profile.csv        → name, headline, location, about, profile_url
#   Positions.csv      → work experience
#   Education.csv      → education history
#   Skills.csv         → skills list
#   Certifications.csv → certifications (if present)

import io
import csv
import zipfile
from typing import Optional

from app.schemas.candidate_schema import (
    LinkedInProfile,
    LinkedInExperience,
    LinkedInEducation,
)


class LinkedInZipParser:

    def _read_csv(self, zf: zipfile.ZipFile, filename: str) -> list[dict]:
        """
        Reads a CSV from the ZIP by filename (case-insensitive match).
        Returns list of row dicts. Returns [] if file not found.
        """
        names = {n.lower(): n for n in zf.namelist()}
        key = filename.lower()

        # also try inside a subfolder e.g. "Basic_LinkedInDataExport_xx/Profile.csv"
        matched = names.get(key)
        if not matched:
            for n in zf.namelist():
                if n.lower().endswith("/" + key) or n.lower() == key:
                    matched = n
                    break

        if not matched:
            return []

        with zf.open(matched) as f:
            content = f.read().decode("utf-8", errors="replace")
            # LinkedIn CSVs sometimes have a 'Notes' header row at top — skip lines before header
            lines = content.splitlines()
            # Find the actual header line (contains comma-separated field names)
            start = 0
            for i, line in enumerate(lines):
                if "," in line and not line.startswith("Note"):
                    start = i
                    break
            cleaned = "\n".join(lines[start:])
            reader = csv.DictReader(io.StringIO(cleaned))
            return [dict(row) for row in reader]

    def _parse_profile(self, rows: list[dict]) -> dict:
        if not rows:
            return {}
        row = rows[0]
        return {
            "full_name": f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip(),
            "headline": row.get("Headline") or None,
            "location": row.get("Geo Location") or row.get("Location") or None,
            "about": row.get("Summary") or None,
            "email": row.get("Email Address") or None,
        }

    def _parse_positions(self, rows: list[dict]) -> tuple[list[LinkedInExperience], Optional[str], Optional[str]]:
        experiences = []
        current_role = None
        current_company = None

        for row in rows:
            title   = row.get("Title", "").strip()
            company = row.get("Company Name", "").strip()
            started = row.get("Started On", "").strip()
            finished = row.get("Finished On", "").strip()
            description = row.get("Description", "").strip() or None

            if not title or not company:
                continue

            duration = started
            if finished:
                duration = f"{started} – {finished}"
            elif started:
                duration = f"{started} – Present"
                # Most recent role with no end date = current
                if current_role is None:
                    current_role = title
                    current_company = company

            experiences.append(LinkedInExperience(
                title=title,
                company=company,
                duration=duration or None,
                description=description,
            ))

        return experiences, current_role, current_company

    def _parse_education(self, rows: list[dict]) -> list[LinkedInEducation]:
        education = []
        for row in rows:
            institution = row.get("School Name", "").strip()
            if not institution:
                continue
            degree_parts = [
                row.get("Degree Name", "").strip(),
                row.get("Field Of Study", "").strip(),
            ]
            degree = ", ".join(p for p in degree_parts if p) or None
            end_date = row.get("End Date", "").strip() or None

            education.append(LinkedInEducation(
                degree=degree,
                institution=institution,
                year=end_date,
            ))
        return education

    def _parse_skills(self, rows: list[dict]) -> list[str]:
        skills = []
        for row in rows:
            skill = row.get("Name", "").strip() or row.get("Skill", "").strip()
            if skill:
                skills.append(skill)
        return skills

    def _parse_certifications(self, rows: list[dict]) -> list[str]:
        certs = []
        for row in rows:
            name = row.get("Name", "").strip() or row.get("Authority", "").strip()
            if name:
                certs.append(name)
        return certs

    def _estimate_experience_years(self, experiences: list[LinkedInExperience]) -> Optional[float]:
        """
        Rough estimate: count total years from durations.
        LinkedIn exports dates as 'Jan 2019' format — we extract years only.
        """
        import re
        total_years = 0.0
        year_pattern = re.compile(r"\b(20\d{2}|19\d{2})\b")

        for exp in experiences:
            if not exp.duration:
                continue
            years_found = year_pattern.findall(exp.duration)
            if len(years_found) >= 2:
                try:
                    total_years += int(years_found[1]) - int(years_found[0])
                except Exception:
                    pass
            elif len(years_found) == 1 and "Present" in exp.duration:
                from datetime import datetime
                try:
                    total_years += datetime.now().year - int(years_found[0])
                except Exception:
                    pass

        return round(total_years, 1) if total_years > 0 else None

    def parse(self, zip_bytes: bytes) -> LinkedInProfile:
        """
        Main entry point.
        Takes raw ZIP bytes, returns a LinkedInProfile ready for DB storage.
        Raises ValueError if ZIP is invalid or missing required Profile.csv.
        """
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            raise ValueError("Uploaded file is not a valid ZIP archive.")

        profile_rows      = self._read_csv(zf, "Profile.csv")
        position_rows     = self._read_csv(zf, "Positions.csv")
        education_rows    = self._read_csv(zf, "Education.csv")
        skill_rows        = self._read_csv(zf, "Skills.csv")
        cert_rows         = self._read_csv(zf, "Certifications.csv")

        if not profile_rows:
            raise ValueError(
                "Profile.csv not found in ZIP. "
                "Please export from LinkedIn → Settings → Data Privacy → Get a copy of your data "
                "and select 'Profile data'."
            )

        profile_data = self._parse_profile(profile_rows)
        experiences, current_role, current_company = self._parse_positions(position_rows)
        education     = self._parse_education(education_rows)
        skills        = self._parse_skills(skill_rows)
        certifications = self._parse_certifications(cert_rows)
        exp_years     = self._estimate_experience_years(experiences)

        return LinkedInProfile(
            full_name              = profile_data.get("full_name") or "Unknown",
            headline               = profile_data.get("headline"),
            location               = profile_data.get("location"),
            email                  = profile_data.get("email"),
            about                  = profile_data.get("about"),
            skills                 = skills,
            experience             = experiences,
            education              = education,
            certifications         = certifications,
            current_role           = current_role,
            current_company        = current_company,
            total_experience_years = exp_years,
            open_to_work           = False,   # candidate sets this themselves after upload
            source                 = "linkedin_zip",
        )


linkedin_zip_parser = LinkedInZipParser()
