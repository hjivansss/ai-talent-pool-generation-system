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
from app.core.database import get_db, SessionLocal



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
from app.services import embedding_service, vector_store
from app.services.embedding_service import embedding_service

router = APIRouter()


MAX_GITHUB_FETCH = 20   # hard cap — prevents rate limit hammering
MAX_EVALUATED   = 7   # hard cap — prevents Ollama timeout

# ── Helper — eliminates repeated LinkedIn profile reconstruction ────────────────

def _record_to_linkedin_profile(r, default_source: str = "linkedin_manual") -> LinkedInProfile:
    return LinkedInProfile(
        full_name=r.full_name, headline=getattr(r, "headline", None),
        location=r.location, email=r.email,
        phone=getattr(r, "phone", None),
        profile_url=getattr(r, "profile_url", None),
        about=getattr(r, "about", None),
        skills=r.skills or [], experience=r.experience or [],
        education=r.education or [], certifications=r.certifications or [],
        total_experience_years=r.total_experience_years,
        current_role=r.current_role, current_company=r.current_company,
        open_to_work=r.open_to_work or False,
        source=getattr(r, "source", None) or default_source,
    )


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

# ── Job Description ─────────────────────────────────────────────────────────────

@router.post("/extract_jd", response_model=ExtractedJDResponse)
async def extract_jd(payload: JobDescriptionRequest):
    try:
        return await jd_extraction_service.extract(payload.job_description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract_and_save_jd", response_model=SavedJDResponse)
async def extract_and_save_jd(payload: JobDescriptionRequest, db: Session = Depends(get_db)):
    try:
        extracted = await jd_extraction_service.extract(payload.job_description)
        saved = job_description_repository.create(
            db=db, original_text=payload.job_description, extracted_data=extracted
        )
        # Embed JD and cache in DB for faster talent pool generation
        jd_text = embedding_service.build_jd_text(saved)
        jd_vector = await embedding_service.embed(jd_text)
        if jd_vector:
            vector_store.ensure_tables(db)
            vector_store.upsert_jd_embedding(db, saved.id, jd_vector)
        return saved
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GitHub candidate search ─────────────────────────────────────────────────────

@router.post("/search/github", response_model=CandidateSearchResponse)
async def search_github_candidates(payload: CandidateSearchRequest):
    try:
        query, candidates = await candidate_search_service.search_github_candidates(
            skills=payload.skills, location=payload.location,
            limit=min(payload.limit, MAX_GITHUB_FETCH),
        )
        return CandidateSearchResponse(query=query, total_found=len(candidates), candidates=candidates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── LinkedIn ────────────────────────────────────────────────────────────────────

@router.post("/ingest/linkedin", response_model=LinkedInIngestResponse)
async def ingest_linkedin_profiles(payload: LinkedInIngestRequest, db: Session = Depends(get_db)):
    saved = []
    for profile in payload.profiles:
        try:
            record = linkedin_repository.create(db=db, profile=profile)
            # Embed and store for semantic retrieval
            unified = normalization_service.from_linkedin(profile)
            vector = await embedding_service.embed(embedding_service.build_candidate_text(unified))
            if vector:
                vector_store.ensure_tables(db)
                vector_store.upsert_candidate_embedding(db, "linkedin", record.id, vector)
            saved.append(profile)
        except Exception as e:
            print(f"[LinkedIn ingest] failed for {profile.full_name}: {e}")
    return LinkedInIngestResponse(total_saved=len(saved), profiles=saved)


@router.post("/linkedin/upload-zip", response_model=LinkedInZipUploadResponse)
async def upload_linkedin_zip(
    file: UploadFile = File(...),
    open_to_work: bool = Query(False),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files accepted.")
    zip_bytes = await file.read()
    if len(zip_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")
    try:
        profile = linkedin_zip_parser.parse(zip_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse ZIP: {e}")

    profile.open_to_work = open_to_work
    try:
        record = linkedin_repository.create(db=db, profile=profile)
        unified = normalization_service.from_linkedin(profile)
        vector = await embedding_service.embed(embedding_service.build_candidate_text(unified))
        if vector:
            vector_store.ensure_tables(db)
            vector_store.upsert_candidate_embedding(db, "linkedin", record.id, vector)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {e}")

    return LinkedInZipUploadResponse(
        message=f"Profile for '{profile.full_name}' parsed and saved successfully.",
        profile=profile,
    )


@router.get("/linkedin/candidates", response_model=list[LinkedInProfile])
def get_linkedin_candidates(open_to_work_only: bool = Query(False), db: Session = Depends(get_db)):
    records = linkedin_repository.get_open_to_work(db) if open_to_work_only else linkedin_repository.get_all(db)
    return [_record_to_linkedin_profile(r) for r in records]


# ── Resume ──────────────────────────────────────────────────────────────────────

@router.post("/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    open_to_work: bool = Query(True),
    db: Session = Depends(get_db),
):
    if not any(file.filename.endswith(ext) for ext in [".pdf", ".docx", ".doc"]):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX accepted.")
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB.")
    try:
        profile = await resume_parser.parse(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {e}")

    profile.open_to_work = open_to_work
    try:
        record = resume_repository.create(db=db, profile=profile, file_name=file.filename)
        unified = normalization_service.from_linkedin(profile)
        vector = await embedding_service.embed(embedding_service.build_candidate_text(unified))
        if vector:
            vector_store.ensure_tables(db)
            vector_store.upsert_candidate_embedding(db, "resume", record.id, vector)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save resume: {e}")

    return ResumeUploadResponse(
        message=f"Resume for '{profile.full_name}' parsed and saved successfully.",
        profile=profile,
    )


@router.get("/resume/candidates", response_model=list[LinkedInProfile])
def get_resume_candidates(db: Session = Depends(get_db)):
    return [_record_to_linkedin_profile(r, "resume") for r in resume_repository.get_all(db)]


# ── Normalization ───────────────────────────────────────────────────────────────

@router.post("/normalize/github", response_model=list[UnifiedCandidate])
async def normalize_github(payload: CandidateSearchRequest):
    try:
        _, candidates = await candidate_search_service.search_github_candidates(
            skills=payload.skills, location=payload.location,
            limit=min(payload.limit, MAX_GITHUB_FETCH),
        )
        return normalization_service.normalize_github_list(candidates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/normalize/linkedin", response_model=list[UnifiedCandidate])
def normalize_linkedin(open_to_work_only: bool = Query(False), db: Session = Depends(get_db)):
    try:
        records = linkedin_repository.get_open_to_work(db) if open_to_work_only else linkedin_repository.get_all(db)
        profiles = [_record_to_linkedin_profile(r) for r in records]
        return normalization_service.normalize_linkedin_list(profiles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/normalize/all", response_model=list[UnifiedCandidate])
async def normalize_all(
    payload: CandidateSearchRequest,
    open_to_work_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        _, github_candidates = await candidate_search_service.search_github_candidates(
            skills=payload.skills, location=payload.location,
            limit=min(payload.limit, MAX_GITHUB_FETCH),
        )
        li_records = linkedin_repository.get_open_to_work(db) if open_to_work_only else linkedin_repository.get_all(db)
        resume_records = resume_repository.get_all(db)

        return normalization_service.deduplicate(
            normalization_service.normalize_github_list(github_candidates) +
            normalization_service.normalize_linkedin_list([_record_to_linkedin_profile(r) for r in li_records]) +
            normalization_service.normalize_linkedin_list([_record_to_linkedin_profile(r, "resume") for r in resume_records])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Talent Pool Generation ──────────────────────────────────────────────────────

@router.post("/talent-pool/generate", response_model=TalentPoolResponse)
async def generate_talent_pool(payload: TalentPoolRequest, db: Session = Depends(get_db)):
    """
    Full pipeline:
    1. Fetch JD → get/compute JD embedding
    2. Vector search → pre-filter LinkedIn + Resume candidates from DB
    3. GitHub search with smart query (language, followers, seniority)
    4. Normalize + deduplicate all sources
    5. Stage 1 scoring with semantic similarity boost
    6. Stage 2 Ollama evaluation on top candidates
    7. Save ranked pool to DB → return paginated
    """
    jd = job_description_repository.get_by_id(db=db, jd_id=payload.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail=f"JD {payload.jd_id} not found.")

    location = payload.location or jd.location

    try:
        # Step 1 — get JD embedding (from cache or compute now)
        jd_vector = vector_store.get_jd_embedding(db, payload.jd_id)
        if not jd_vector:
            jd_vector = await embedding_service.embed(embedding_service.build_jd_text(jd))
            if jd_vector:
                vector_store.ensure_tables(db)
                vector_store.upsert_jd_embedding(db, payload.jd_id, jd_vector)

        # Step 2 — vector pre-filter for LinkedIn + Resume candidates
        similarity_map: dict[str, float] = {}
        if jd_vector:
            similar = vector_store.find_similar_candidates(db, jd_vector, top_k=20)
            similar_li_ids  = {cid for ctype, cid, _ in similar if ctype == "linkedin"}
            similar_res_ids = {cid for ctype, cid, _ in similar if ctype == "resume"}
            for ctype, cid, sim in similar:
                similarity_map[f"{ctype}:{cid}"] = sim
        else:
            similar_li_ids  = None   # None = load all
            similar_res_ids = None

        # Step 3 — load LinkedIn + Resume from DB (pre-filtered or all)
        li_records = linkedin_repository.get_all(db)
        if similar_li_ids is not None:
            li_records = [r for r in li_records if r.id in similar_li_ids]

        resume_records = resume_repository.get_all(db)
        if similar_res_ids is not None:
            resume_records = [r for r in resume_records if r.id in similar_res_ids]
            
        # We're done reading from `db` for this request. Close it now instead of
        # leaving it open-but-idle through the GitHub + Ollama pipeline below —
        # Neon drops idle SSL connections, and an idle-but-open session here just
        # means FastAPI's teardown trips over a dead connection later. Closing
        # explicitly is safe/idempotent (get_db's finally will close() again, a no-op).
        db.close()

        # Step 4 — GitHub search with smart query
        _, github_candidates = await candidate_search_service.search_github_candidates(
            skills=jd.required_skills or [],
            location=location,
            limit=min(payload.limit, MAX_GITHUB_FETCH),
            seniority_level=jd.seniority_level,
            github_language=payload.github_language,
            min_followers=payload.min_followers,
            min_repos=payload.min_repos,
        )

        # Step 5 — normalize all three sources
        unified_github   = normalization_service.normalize_github_list(github_candidates)
        unified_linkedin = normalization_service.normalize_linkedin_list(
            [_record_to_linkedin_profile(r) for r in li_records]
        )
        unified_resume = normalization_service.normalize_linkedin_list(
            [_record_to_linkedin_profile(r, "resume") for r in resume_records]
        )
        all_candidates = normalization_service.deduplicate(
            unified_github + unified_linkedin + unified_resume
        )

        # Build name → similarity map for scoring
        named_similarity: dict[str, float] = {}
        for r in li_records:
            key = f"linkedin:{r.id}"
            if key in similarity_map:
                named_similarity[r.full_name] = similarity_map[key]
        for r in resume_records:
            key = f"resume:{r.id}"
            if key in similarity_map:
                named_similarity[r.full_name] = similarity_map[key]

        # Step 6 — Stage 1 filter
        filtered = matching_service.filter_candidates(
            candidates=all_candidates, jd=jd,
            min_score=payload.min_score,
            similarity_map=named_similarity,
        )

        # Step 7 — Stage 2 Ollama evaluation
        evaluated = await evaluation_service.evaluate_all(
            filtered=filtered, jd=jd, max_evaluated=MAX_EVALUATED,
        )

        # Step 8 — Save and paginate
        # NOTE: `db` was checked out at the start of this request and has likely
        # sat idle through minutes of GitHub/Ollama calls above. Neon (serverless
        # Postgres) drops idle SSL connections, so we open a fresh short-lived
        # session here rather than reuse a possibly-dead one.
        write_db = SessionLocal()
        try:
            pool = talent_pool_repository.create(
                db=write_db, jd_id=payload.jd_id, job_role=jd.job_role,
                candidates=evaluated,
                filter_params={
                    "location": location, "limit": payload.limit,
                    "min_score": payload.min_score,
                    "github_language": payload.github_language,
                    "min_followers": payload.min_followers,
                },
            )
        finally:
            write_db.close()

        total_pages = max(1, math.ceil(len(evaluated) / payload.page_size))
        start = (payload.page - 1) * payload.page_size
        return TalentPoolResponse(
            pool_id=pool.id, jd_id=payload.jd_id, job_role=jd.job_role,
            generated_at=pool.generated_at, total_candidates=len(evaluated),
            page=payload.page, page_size=payload.page_size, total_pages=total_pages,
            candidates=evaluated[start:start + payload.page_size],
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
    pool = talent_pool_repository.get_by_id(db=db, pool_id=pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Talent pool {pool_id} not found.")
    all_candidates = [CandidateEvaluation(**c) for c in pool.candidates]
    total_pages = max(1, math.ceil(len(all_candidates) / page_size))
    start = (page - 1) * page_size
    return TalentPoolResponse(
        pool_id=pool.id, jd_id=pool.jd_id, job_role=pool.job_role,
        generated_at=pool.generated_at, total_candidates=pool.total_candidates,
        page=page, page_size=page_size, total_pages=total_pages,
        candidates=all_candidates[start:start + page_size],
    )


@router.get("/talent-pool/jd/{jd_id}/summary", response_model=list[TalentPoolSummary])
def get_talent_pool_summaries(jd_id: int, db: Session = Depends(get_db)):
    pools = talent_pool_repository.get_by_jd_id(db=db, jd_id=jd_id)
    if not pools:
        raise HTTPException(status_code=404, detail=f"No pools found for JD {jd_id}.")
    return [
        TalentPoolSummary(
            pool_id=p.id, jd_id=p.jd_id, job_role=p.job_role,
            generated_at=p.generated_at, total_candidates=p.total_candidates,
            tier1_count=p.tier1_count, tier2_count=p.tier2_count, tier3_count=p.tier3_count,
        )
        for p in pools
    ]
