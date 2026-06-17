from fastapi import FastAPI

from app.core.config import settings
from app.api.router import router as api_router 

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered talent pool search and candidate ranking backend",
)

#Adding the routes from app/api/ v1/router.py for better organization 
app.include_router(
    api_router, 
    prefix="/api",
    tags=["API"]
)



@app.get("/")
def root():
    return {
        "message": "AI Talent Pool Search API is running",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


