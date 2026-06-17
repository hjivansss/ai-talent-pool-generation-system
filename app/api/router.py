#This will maintain the api routes for better organization (main.py will be less cluttered)
from fastapi import APIRouter
from app.integrations.ollama_client import ollama_client
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