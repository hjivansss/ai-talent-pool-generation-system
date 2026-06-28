#This will maintain the api routes for better organization (main.py will be less cluttered)
from fastapi import APIRouter, HTTPException , Depends  , UploadFile, File, Query
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
    LinkedInZipUploadResponse,
)

from app.services.candidate_search_service import candidate_search_service
from app.repositories.linkedin_repository import linkedin_repository
from app.services.linkedin_zip_parser import linkedin_zip_parser
from app.schemas.unified_candidate import UnifiedCandidate
from app.services.normalization_service import normalization_service

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


# ── LinkedIn: ZIP export upload ─────────────────────────────────────────────────

@router.post("/linkedin/upload-zip", response_model=LinkedInZipUploadResponse)
async def upload_linkedin_zip(
    file: UploadFile = File(...),
    open_to_work: bool = Query(False, description="Is this candidate open to work?"),
    db: Session = Depends(get_db),
):
    """
    Candidate uploads their LinkedIn data export ZIP file.

    How to get the ZIP:
    LinkedIn → Settings → Data Privacy → Get a copy of your data
    → Select 'Profile data only' → Download when ready (takes ~10 mins).

    The ZIP is parsed in memory — raw file is never stored.
    Only the structured profile data is saved to the database.
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    zip_bytes = await file.read()

    # 5MB sanity limit — LinkedIn exports are typically under 1MB
    if len(zip_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")

    try:
        profile = linkedin_zip_parser.parse(zip_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse ZIP: {str(e)}")

    # Allow candidate to set their open_to_work status at upload time
    profile.open_to_work = open_to_work

    try:
        linkedin_repository.create(db=db, profile=profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")

    return LinkedInZipUploadResponse(
        message=f"Profile for '{profile.full_name}' parsed and saved successfully.",
        profile=profile,
    )


# ── LinkedIn: fetch stored profiles ────────────────────────────────────────────

@router.get("/linkedin/candidates", response_model=list[LinkedInProfile])
def get_linkedin_candidates(
    open_to_work_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Fetch all stored LinkedIn profiles.
    Use ?open_to_work_only=true to filter candidates actively looking.
    """
    if open_to_work_only:
        records = linkedin_repository.get_open_to_work(db=db)
    else:
        records = linkedin_repository.get_all(db=db)

    return [
        LinkedInProfile(
            full_name              = r.full_name,
            headline               = r.headline,
            location               = r.location,
            email                  = r.email,
            phone                  = r.phone,
            profile_url            = r.profile_url,
            about                  = r.about,
            skills                 = r.skills or [],
            experience             = r.experience or [],
            education              = r.education or [],
            certifications         = r.certifications or [],
            total_experience_years = r.total_experience_years,
            current_role           = r.current_role,
            current_company        = r.current_company,
            open_to_work           = r.open_to_work or False,
            source                 = r.source or "linkedin_manual",
        )
        for r in records
    ]



# ── Phase 5: Normalization ──────────────────────────────────────────────────────

@router.post("/normalize/github", response_model=list[UnifiedCandidate])
async def normalize_github(payload: CandidateSearchRequest):
    """
    Searches GitHub candidates and returns them as normalized UnifiedCandidates.
    Ready for Phase 6 semantic matching.
    """
    try:
        _, candidates = await candidate_search_service.search_github_candidates(
            skills=payload.skills,
            location=payload.location,
            limit=payload.limit,
        )
        return normalization_service.normalize_github_list(candidates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/normalize/linkedin", response_model=list[UnifiedCandidate])
def normalize_linkedin(
    open_to_work_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Fetches stored LinkedIn profiles and returns them as normalized UnifiedCandidates.
    Ready for Phase 6 semantic matching.
    """
    try:
        if open_to_work_only:
            records = linkedin_repository.get_open_to_work(db=db)
        else:
            records = linkedin_repository.get_all(db=db)

        profiles = [
            LinkedInProfile(
                full_name              = r.full_name,
                headline               = r.headline,
                location               = r.location,
                email                  = r.email,
                phone                  = r.phone,
                profile_url            = r.profile_url,
                about                  = r.about,
                skills                 = r.skills or [],
                experience             = r.experience or [],
                education              = r.education or [],
                certifications         = r.certifications or [],
                total_experience_years = r.total_experience_years,
                current_role           = r.current_role,
                current_company        = r.current_company,
                open_to_work           = r.open_to_work or False,
                source                 = r.source or "linkedin_manual",
            )
            for r in records
        ]
        return normalization_service.normalize_linkedin_list(profiles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/normalize/all", response_model=list[UnifiedCandidate])
async def normalize_all(
    payload: CandidateSearchRequest,
    open_to_work_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Fetches GitHub candidates + stored LinkedIn profiles,
    normalizes both, deduplicates by email/name, returns one unified list.
    This is the main input for Phase 6 semantic matching.
    """
    try:
        # GitHub
        _, github_candidates = await candidate_search_service.search_github_candidates(
            skills=payload.skills,
            location=payload.location,
            limit=payload.limit,
        )
        unified_github = normalization_service.normalize_github_list(github_candidates)

        # LinkedIn
        if open_to_work_only:
            li_records = linkedin_repository.get_open_to_work(db=db)
        else:
            li_records = linkedin_repository.get_all(db=db)

        linkedin_profiles = [
            LinkedInProfile(
                full_name              = r.full_name,
                headline               = r.headline,
                location               = r.location,
                email                  = r.email,
                phone                  = r.phone,
                profile_url            = r.profile_url,
                about                  = r.about,
                skills                 = r.skills or [],
                experience             = r.experience or [],
                education              = r.education or [],
                certifications         = r.certifications or [],
                total_experience_years = r.total_experience_years,
                current_role           = r.current_role,
                current_company        = r.current_company,
                open_to_work           = r.open_to_work or False,
                source                 = r.source or "linkedin_manual",
            )
            for r in li_records
        ]
        unified_linkedin = normalization_service.normalize_linkedin_list(linkedin_profiles)

        # Combine + deduplicate
        all_candidates = unified_github + unified_linkedin
        return normalization_service.deduplicate(all_candidates)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
