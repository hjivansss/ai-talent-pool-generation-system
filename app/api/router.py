#This will maintain the api routes for better organization (main.py will be less cluttered)
from fastapi import APIRouter, HTTPException , Depends
from app.integrations.ollama_client import ollama_client

from app.services.jd_extraction_service import jd_extraction_service
from app.schemas.jd_schema import (
    JobDescriptionRequest, 
    ExtractedJDResponse , 
    SavedJDResponse)

from sqlalchemy.orm import Session
from app.repositories.job_description_repository import job_description_repository
from app.core.database import get_db


from app.schemas.candidate_schema import (
    CandidateSearchRequest,
    CandidateSearchResponse,
    LinkedInProfile,
    LinkedInIngestRequest,
    LinkedInIngestResponse,
)

from app.services.candidate_search_service import candidate_search_service
from app.repositories.linkedin_repository import linkedin_repository


router = APIRouter()

@router.get("/")
def api_root():
    return{
        "message" : "Api  is running"
    }

@router.get("/health")
def health_check():
    return {
        "status": "healthy"
    }

@router.post("/test_ollama")
async def test_ollama():
    response = await ollama_client.generate(
        "Say hello. Return only one short sentence."
    )

    return {
        "response": response
    }

@router.post("/extract_jd",response_model=ExtractedJDResponse)
async def extract_jd(payload: JobDescriptionRequest):
    try:
        result = await jd_extraction_service.extract(
            payload.job_description
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

#endpoint that extracts JD and saves it into Neon.
@router.post("/extract_and_save_jd", response_model=SavedJDResponse)
async def extract_and_save_jd(
    payload: JobDescriptionRequest,
    db: Session = Depends(get_db)
):
    try:
        extracted_data = await jd_extraction_service.extract(
            payload.job_description
        )

        saved_jd = job_description_repository.create(
            db=db,
            original_text=payload.job_description,
            extracted_data=extracted_data
        )

        return saved_jd

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    

# ── GitHub candidate search ─────────────────────────────────────────────────────

@router.post("/search/github", response_model=CandidateSearchResponse)
async def search_github_candidates(payload: CandidateSearchRequest):
    try:
        query, candidates = await candidate_search_service.search_github_candidates(
            skills=payload.skills,
            location=payload.location,
            limit=payload.limit,
        )
        return CandidateSearchResponse(
            query=query,
            total_found=len(candidates),
            candidates=candidates,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── LinkedIn manual ingestion ───────────────────────────────────────────────────

@router.post("/ingest/linkedin", response_model=LinkedInIngestResponse)
async def ingest_linkedin_profiles(
    payload: LinkedInIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Recruiter manually enters LinkedIn profiles here.
    Each profile is validated and saved to the linkedin_profiles table.

    Key field: set open_to_work: true to flag candidates actively looking.
    These will be prioritised in Phase 6 matching.
    """
    saved = []
    for profile in payload.profiles:
        try:
            linkedin_repository.create(db=db, profile=profile)
            saved.append(profile)
        except Exception as e:
            # Skip failed saves, don't abort the whole batch
            print(f"[LinkedIn ingest] failed to save {profile.full_name}: {e}")

    return LinkedInIngestResponse(total_saved=len(saved), profiles=saved)


@router.get("/linkedin/candidates", response_model=list[LinkedInProfile])
def get_linkedin_candidates(
    open_to_work_only: bool = False,
    db: Session = Depends(get_db),
):
    """
    Fetch stored LinkedIn profiles.
    Pass ?open_to_work_only=true to get only candidates actively looking.
    """
    if open_to_work_only:
        records = linkedin_repository.get_open_to_work(db=db)
    else:
        records = linkedin_repository.get_all(db=db)

    return [
        LinkedInProfile(
            full_name=r.full_name,
            headline=r.headline,
            location=r.location,
            email=r.email,
            phone=r.phone,
            profile_url=r.profile_url,
            about=r.about,
            skills=r.skills or [],
            experience=r.experience or [],
            education=r.education or [],
            certifications=r.certifications or [],
            total_experience_years=r.total_experience_years,
            current_role=r.current_role,
            current_company=r.current_company,
            open_to_work=r.open_to_work or False,
        )
        for r in records
    ]
