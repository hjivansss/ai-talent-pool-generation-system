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
     ResumeUploadResponse,
)

from app.services.candidate_search_service import candidate_search_service
from app.repositories.linkedin_repository import linkedin_repository
from app.services.linkedin_zip_parser import linkedin_zip_parser
from app.services.resume_parser import resume_parser
from app.schemas.unified_candidate import UnifiedCandidate
from app.services.normalization_service import normalization_service
from app.repositories.talent_pool_repository import talent_pool_repository
from app.services.matching_service import matching_service
from app.services.evaluation_service import evaluation_service
import math
from app.repositories.resume_repository import resume_repository

from app.schemas.talent_pool_schema import (
    TalentPoolRequest,
    TalentPoolResponse,
    TalentPoolSummary,
    CandidateEvaluation,
)

router = APIRouter()


MAX_GITHUB_FETCH = 20   # hard cap — prevents rate limit hammering
MAX_EVALUATED   = 3    # hard cap — prevents Ollama timeout

#----------------------------------------- APIs--------------------------------------------------------------
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


# ── Phase 6: Talent Pool Generation ────────────────────────────────────────────

@router.post("/talent-pool/generate", response_model=TalentPoolResponse)
async def generate_talent_pool(
    payload: TalentPoolRequest,
    db: Session = Depends(get_db),
):
    """
    Main Phase 6 endpoint. Full pipeline in one call:
    1. Fetch JD from DB
    2. Search + normalize GitHub and LinkedIn candidates
    3. Stage 1: rule-based filter and scoring
    4. Stage 2: Ollama AI evaluation on filtered candidates
    5. Rank by overall_fit_score
    6. Save ranked pool to DB
    7. Return paginated results

    Subsequent page views use GET /talent-pool/{pool_id} — no re-evaluation.
    """
    # Step 1 — fetch JD
    jd = job_description_repository.get_by_id(db=db, jd_id=payload.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail=f"Job description {payload.jd_id} not found.")

    location = payload.location or jd.location

    try:
        # Step 2 — fetch and normalize candidates
        _, github_candidates = await candidate_search_service.search_github_candidates(
            skills=jd.required_skills or [],
            location=location,
            limit=min(payload.limit, MAX_GITHUB_FETCH),
        )
        unified_github = normalization_service.normalize_github_list(github_candidates)

        li_records = linkedin_repository.get_all(db)
        linkedin_profiles = [
            LinkedInProfile(
                full_name=r.full_name, headline=r.headline, location=r.location,
                email=r.email, phone=r.phone, profile_url=r.profile_url,
                about=r.about, skills=r.skills or [], experience=r.experience or [],
                education=r.education or [], certifications=r.certifications or [],
                total_experience_years=r.total_experience_years,
                current_role=r.current_role, current_company=r.current_company,
                open_to_work=r.open_to_work or False, source=r.source or "linkedin_manual",
            )
            for r in li_records
        ]
        unified_linkedin = normalization_service.normalize_linkedin_list(linkedin_profiles)
        all_candidates = normalization_service.deduplicate(unified_github + unified_linkedin)

        # Step 3 — Stage 1 filter
        filtered = matching_service.filter_candidates(
            candidates=all_candidates,
            jd=jd,
            min_score=payload.min_score,
        )

        # Step 4 — Stage 2 Ollama evaluation
        evaluated = await evaluation_service.evaluate_all(
            filtered_candidates=filtered,
            jd=jd,
            max_evaluated=MAX_EVALUATED,
        )

        # Step 5 — Save to DB
        pool = talent_pool_repository.create(
            db=db,
            jd_id=payload.jd_id,
            job_role=jd.job_role,
            candidates=evaluated,
            filter_params={
                "location": location,
                "limit": payload.limit,
                "min_score": payload.min_score,
            },
        )

        # Step 6 — Paginate and return
        total_pages = max(1, math.ceil(len(evaluated) / payload.page_size))
        start = (payload.page - 1) * payload.page_size
        end   = start + payload.page_size
        page_candidates = evaluated[start:end]

        return TalentPoolResponse(
            pool_id           = pool.id,
            jd_id             = payload.jd_id,
            job_role          = jd.job_role,
            generated_at      = pool.generated_at,
            total_candidates  = len(evaluated),
            page              = payload.page,
            page_size         = payload.page_size,
            total_pages       = total_pages,
            candidates        = page_candidates,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/talent-pool/{pool_id}", response_model=TalentPoolResponse)
def get_talent_pool(
    pool_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Fetch a previously generated talent pool by pool_id.
    Paginated — no re-evaluation, reads directly from DB.
    Use this for page 2, page 3 etc after initial generation.
    """
    pool = talent_pool_repository.get_by_id(db=db, pool_id=pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Talent pool {pool_id} not found.")

    all_candidates = [CandidateEvaluation(**c) for c in pool.candidates]
    total_pages = max(1, math.ceil(len(all_candidates) / page_size))
    start = (page - 1) * page_size
    end   = start + page_size

    return TalentPoolResponse(
        pool_id          = pool.id,
        jd_id            = pool.jd_id,
        job_role         = pool.job_role,
        generated_at     = pool.generated_at,
        total_candidates = pool.total_candidates,
        page             = page,
        page_size        = page_size,
        total_pages      = total_pages,
        candidates       = all_candidates[start:end],
    )


@router.get("/talent-pool/jd/{jd_id}/summary", response_model=list[TalentPoolSummary])
def get_talent_pool_summaries(jd_id: int, db: Session = Depends(get_db)):
    """
    Lists all talent pools generated for a JD, newest first.
    Use this to pick which pool_id to view, or to compare runs.
    """
    pools = talent_pool_repository.get_by_jd_id(db=db, jd_id=jd_id)
    if not pools:
        raise HTTPException(status_code=404, detail=f"No talent pools found for JD {jd_id}.")
    return [
        TalentPoolSummary(
            pool_id          = p.id,
            jd_id            = p.jd_id,
            job_role         = p.job_role,
            generated_at     = p.generated_at,
            total_candidates = p.total_candidates,
            tier1_count      = p.tier1_count,
            tier2_count      = p.tier2_count,
            tier3_count      = p.tier3_count,
        )
        for p in pools
    ]

# ── Phase 7: Resume Upload ──────────────────────────────────────────────────────
@router.post("/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    open_to_work: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Candidate uploads their resume as PDF or DOCX.
    File is parsed in memory via pdfplumber/python-docx + Ollama.
    Structured profile saved to resumes table.
    Flows into talent pool generation automatically.
    """
    allowed = [".pdf", ".docx", ".doc"]
    if not any(file.filename.endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files accepted.")

    file_bytes = await file.read()

    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum 10MB.")

    try:
        profile = await resume_parser.parse(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

    profile.open_to_work = open_to_work

    try:
        resume_repository.create(db=db, profile=profile, file_name=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save resume: {str(e)}")

    return ResumeUploadResponse(
        message=f"Resume for '{profile.full_name}' parsed and saved successfully.",
        profile=profile,
    )


@router.get("/resume/candidates", response_model=list[LinkedInProfile])
def get_resume_candidates(db: Session = Depends(get_db)):
    """Fetch all stored resume profiles."""
    records = resume_repository.get_all(db=db)
    return [
        LinkedInProfile(
            full_name=r.full_name,
            headline=r.headline,
            location=r.location,
            email=r.email,
            phone=r.phone,
            skills=r.skills or [],
            experience=r.experience or [],
            education=r.education or [],
            certifications=r.certifications or [],
            total_experience_years=r.total_experience_years,
            current_role=r.current_role,
            current_company=r.current_company,
            open_to_work=r.open_to_work or True,
            source="resume",
        )
        for r in records
    ]
