#This will maintain the api routes for better organization (main.py will be less cluttered)
from fastapi import APIRouter, HTTPException
from app.integrations.ollama_client import ollama_client

from app.services.jd_extraction_service import jd_extraction_service
from app.schemas.jd_schema import JobDescriptionRequest, ExtractedJDResponse

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