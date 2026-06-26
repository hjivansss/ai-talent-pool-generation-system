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


from app.schemas.candidate_schema import CandidateSearchRequest, CandidateSearchResponse
from app.services.candidate_search_service import candidate_search_service

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
    
    
#GitHub candidate search
@router.post("/search/github", response_model=CandidateSearchResponse)
async def search_github_candidates(payload: CandidateSearchRequest):
    try:
        query, candidates = await candidate_search_service.search_github_candidates(
            skills=payload.skills,
            location=payload.location,
            limit=payload.limit
        )

        return CandidateSearchResponse(
            query=query,
            total_found=len(candidates),
            candidates=candidates
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))