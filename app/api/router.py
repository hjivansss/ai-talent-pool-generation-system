#This will maintain the api routes for better organization (main.py will be less cluttered)
from fastapi import APIRouter, HTTPException , Depends  , UploadFile, File, Query
from app.integrations.ollama_client import ollama_client

from app.services.jd_extraction_service import jd_extraction_service
from app.schemas.jd_schema import (
    JDListItem,
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
from app.services.auth_service import require_role
from app.integrations.cloudinary_client import cloudinary_client
from app.models.user import User

from app.schemas.talent_pool_schema import (
    TalentPoolRequest,
    TalentPoolResponse,
    TalentPoolSummary,
    CandidateEvaluation,
)
from app.services import embedding_service, vector_store
from app.services.embedding_service import embedding_service
from app.core.timing import timed, Timer
from app.core.config import settings

router = APIRouter()


MAX_GITHUB_FETCH = 20   # hard cap — prevents rate limit hammering
MAX_EVALUATED    = settings.MAX_EVALUATED       # candidates considered for final pool
LLM_SCORE_THRESHOLD = settings.LLM_SCORE_THRESHOLD  # below this, skip Ollama — see evaluation_service

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
        file_url=getattr(r, "file_url", None),
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
async def extract_jd(payload: JobDescriptionRequest, current_user: User = Depends(require_role("recruiter"))):
    try:
        return await jd_extraction_service.extract(payload.job_description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract_and_save_jd", response_model=SavedJDResponse)
async def extract_and_save_jd(
    payload: JobDescriptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
    try:
        extracted = await jd_extraction_service.extract(payload.job_description)
        saved = job_description_repository.create(
            db=db, original_text=payload.job_description, extracted_data=extracted,
            created_by_user_id=current_user.id,
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
async def search_github_candidates(
    payload: CandidateSearchRequest,
    current_user: User = Depends(require_role("recruiter")),
):
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
async def ingest_linkedin_profiles(
    payload: LinkedInIngestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
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
    current_user: User = Depends(require_role("recruiter", "candidate")),
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
        # A candidate uploading their own profile owns it; a recruiter
        # uploading on someone's behalf does not — that record stays
        # "unclaimed" until the actual candidate registers and it's linked.
        candidate_owner_id = current_user.id if current_user.role == "candidate" else None
        record, is_new = linkedin_repository.create_or_update(
            db=db, profile=profile,
            uploaded_by_user_id=current_user.id,
            candidate_owner_user_id=candidate_owner_id,
        )
        unified = normalization_service.from_linkedin(profile)
        vector = await embedding_service.embed(embedding_service.build_candidate_text(unified))
        if vector:
            vector_store.ensure_tables(db)
            vector_store.upsert_candidate_embedding(db, "linkedin", record.id, vector)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {e}")

    return LinkedInZipUploadResponse(
        message=(
            f"Profile for '{profile.full_name}' saved successfully."
            if is_new else
            f"Profile for '{profile.full_name}' already existed — updated existing record."
        ),
        profile=profile,
    )


@router.get("/linkedin/candidates", response_model=list[LinkedInProfile])
def get_linkedin_candidates(
    open_to_work_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
    records = linkedin_repository.get_open_to_work(db) if open_to_work_only else linkedin_repository.get_all(db)
    return [_record_to_linkedin_profile(r) for r in records]


# ── Resume ──────────────────────────────────────────────────────────────────────


@router.post("/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    open_to_work: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter", "candidate")),
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
        # Push the raw file to Cloudinary so recruiters can view the original
        # document later, not just the parsed fields. Doesn't raise on
        # failure — see cloudinary_client.py — the upload still succeeds
        # even if file storage is down or unconfigured.
        file_url = cloudinary_client.upload_resume_file(file_bytes, file.filename)

        candidate_owner_id = current_user.id if current_user.role == "candidate" else None
        record, is_new = resume_repository.create_or_update(
            db=db, profile=profile, file_name=file.filename, file_url=file_url,
            uploaded_by_user_id=current_user.id,
            candidate_owner_user_id=candidate_owner_id,
        )
        unified = normalization_service.from_linkedin(profile)
        vector = await embedding_service.embed(embedding_service.build_candidate_text(unified))
        if vector:
            vector_store.ensure_tables(db)
            vector_store.upsert_candidate_embedding(db, "resume", record.id, vector)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save resume: {e}")

    return ResumeUploadResponse(
        message=(
            f"Resume for '{profile.full_name}' saved successfully."
            if is_new else
            f"Resume for '{profile.full_name}' already existed — updated existing record."
        ),
        profile=profile,
    )


@router.get("/resume/candidates", response_model=list[LinkedInProfile])
def get_resume_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
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
async def generate_talent_pool(
    payload: TalentPoolRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
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
    # Scoped to owner — a recruiter can only generate a pool for their own
    # JD, and a 404 here (rather than 403) deliberately doesn't reveal
    # whether a JD with this id exists at all under someone else's account.
    jd = job_description_repository.get_by_id(db=db, jd_id=payload.jd_id, owner_user_id=current_user.id)
    if not jd:
        raise HTTPException(status_code=404, detail=f"JD {payload.jd_id} not found.")
    db.expunge(jd)
    location = payload.location or jd.location

    pipeline_timer = Timer(f"[TALENT-POOL TOTAL] jd_id={payload.jd_id}")

    try:
        # Step 1 — get JD embedding (from cache or compute now)
        with timed("Step 1 — JD embedding (cache lookup / compute)"):
            jd_vector = vector_store.get_jd_embedding(db, payload.jd_id)
            if not jd_vector:
                jd_vector = await embedding_service.embed(embedding_service.build_jd_text(jd))
                if jd_vector:
                    vector_store.ensure_tables(db)
                    vector_store.upsert_jd_embedding(db, payload.jd_id, jd_vector)

        # Step 2 — compute similarity scores for LinkedIn + Resume candidates.
        # NOTE (2026-07-19 fix): this used to be a HARD top_k=20 pre-filter that
        # dropped any candidate not in the top 20 by cosine similarity *before*
        # Stage 1 rule-based scoring ever ran — meaning a candidate with a
        # perfect skill match but slightly different embedded phrasing could be
        # silently excluded and never get a justification. Stage 1 scoring is
        # cheap, in-memory, pure Python (Step 6 measured at 0.00-0.05s even for
        # 16+ candidates) — there's no latency reason to pre-filter before it.
        # Similarity is now used only as a scoring signal (15% weight, see
        # matching_service.score), applied to the full candidate pool.
        with timed("Step 2 — Vector similarity scoring (DB)"):
            similarity_map: dict[str, float] = {}
            if jd_vector:
                similar = vector_store.find_similar_candidates(db, jd_vector, top_k=1000)
                for ctype, cid, sim in similar:
                    similarity_map[f"{ctype}:{cid}"] = sim

        # Step 3 — load LinkedIn + Resume from DB (no pre-filter), per source toggle
        with timed("Step 3 — Load LinkedIn + Resume records (DB)"):
            li_records = linkedin_repository.get_all(db) if payload.include_linkedin else []
            resume_records = resume_repository.get_all(db) if payload.include_resume else []

        # Fetch prior pools' candidate identities now, while `db` is still open,
        # for the cross-regeneration exclusion in Step 5.5 below.
        prior_seen_emails: set[str] = set()
        prior_seen_names: set[str] = set()
        if payload.exclude_previously_shown:
            with timed("Step 3.5 — Load prior pool identities (DB)"):
                prior_pools = talent_pool_repository.get_by_jd_id(db, payload.jd_id, owner_user_id=current_user.id)
                prior_candidates = [c for pool in prior_pools for c in (pool.candidates or [])]
                prior_seen_emails, prior_seen_names = normalization_service.seen_identities_from_prior_pools(
                    prior_candidates
                )
            print(f"[TIMING] prior pools for jd_id={payload.jd_id}: {len(prior_pools)} "
                  f"({len(prior_candidates)} previously-surfaced candidates)")

        print(f"[TIMING] pool sizes → linkedin={len(li_records)} resume={len(resume_records)}")

        # We're done reading from `db` for this request. Close it now instead of
        # leaving it open-but-idle through the GitHub + Ollama pipeline below —
        # Neon drops idle SSL connections, and an idle-but-open session here just
        # means FastAPI's teardown trips over a dead connection later. Closing
        # explicitly is safe/idempotent (get_db's finally will close() again, a no-op).
        db.close()

        # Step 4 — GitHub search with smart query (skipped entirely if disabled —
        # real latency savings, not a post-hoc filter on fetched results)
        if payload.include_github:
            with timed(f"Step 4 — GitHub search + fetch (limit={min(payload.limit, MAX_GITHUB_FETCH)})"):
                _, github_candidates = await candidate_search_service.search_github_candidates(
                    skills=jd.required_skills or [],
                    location=location,
                    limit=min(payload.limit, MAX_GITHUB_FETCH),
                    seniority_level=jd.seniority_level,
                    github_language=payload.github_language,
                    min_followers=payload.min_followers,
                    min_repos=payload.min_repos,
                )
        else:
            github_candidates = []
            print("[TIMING] Step 4 — GitHub search + fetch: skipped (include_github=False)")
        print(f"[TIMING] github candidates fetched: {len(github_candidates)}")

        # Step 5 — normalize all three sources
        with timed("Step 5 — Normalize + deduplicate"):
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

        # Step 5.5 — exclude candidates already surfaced in a prior pool for this JD
        if payload.exclude_previously_shown and (prior_seen_emails or prior_seen_names):
            with timed("Step 5.5 — Exclude previously-surfaced candidates"):
                before = len(all_candidates)
                all_candidates = [
                    c for c in all_candidates
                    if not normalization_service.is_previously_seen(c, prior_seen_emails, prior_seen_names)
                ]
                print(f"[TIMING] excluded {before - len(all_candidates)} candidates "
                      f"already seen in a prior pool for jd_id={payload.jd_id}")

        # Step 6 — Stage 1 filter
        with timed(f"Step 6 — Stage 1 rule-based scoring ({len(all_candidates)} candidates)"):
            filtered = matching_service.filter_candidates(
                candidates=all_candidates, jd=jd,
                min_score=payload.min_score,
                similarity_map=named_similarity,
            )
        print(f"[TIMING] candidates passing stage 1: {len(filtered)} "
              f"(will evaluate top {min(len(filtered), MAX_EVALUATED)})")

        # Step 7 — Stage 2 Ollama evaluation
        # Only candidates with composite Stage-1 score >= LLM_SCORE_THRESHOLD get
        # an actual Ollama call; the rest are evaluated from Stage-1 data directly
        # (see evaluation_service._template_evaluation). filtered is already
        # sorted by composite_score descending, so the strongest candidates
        # always get the real LLM evaluation first.
        with timed(f"Step 7 — Stage 2 Ollama evaluation (max {MAX_EVALUATED}, "
                    f"llm_threshold={LLM_SCORE_THRESHOLD})"):
            evaluated = await evaluation_service.evaluate_all(
                filtered=filtered, jd=jd, max_evaluated=MAX_EVALUATED,
                llm_score_threshold=LLM_SCORE_THRESHOLD,
            )

        # Step 8 — Save and paginate
        # NOTE: `db` was checked out at the start of this request and has likely
        # sat idle through minutes of GitHub/Ollama calls above. Neon (serverless
        # Postgres) drops idle SSL connections, so we open a fresh short-lived
        # session here rather than reuse a possibly-dead one.
        with timed("Step 8 — Save talent pool (DB write)"):
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
                    created_by_user_id=current_user.id,
                )
            finally:
                write_db.close()

        total_pages = max(1, math.ceil(len(evaluated) / payload.page_size))
        start = (payload.page - 1) * payload.page_size

        pipeline_timer.stop()

        return TalentPoolResponse(
            pool_id=pool.id, jd_id=payload.jd_id, job_role=jd.job_role,
            generated_at=pool.generated_at, total_candidates=len(evaluated),
            page=payload.page, page_size=payload.page_size, total_pages=total_pages,
            candidates=evaluated[start:start + payload.page_size],
        )

    except Exception as e:
        pipeline_timer.stop()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/talent-pool/{pool_id}", response_model=TalentPoolResponse)
def get_talent_pool(
    pool_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
    pool = talent_pool_repository.get_by_id(db=db, pool_id=pool_id, owner_user_id=current_user.id)
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
def get_talent_pool_summaries(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
    pools = talent_pool_repository.get_by_jd_id(db=db, jd_id=jd_id, owner_user_id=current_user.id)
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

@router.get("/jd", response_model=list[JDListItem])
def list_job_descriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("recruiter")),
):
    return job_description_repository.get_all(db, owner_user_id=current_user.id)