from fastapi import FastAPI

from app.core.config import settings
from app.api.router import router as api_router 

from app.core.database import Base, engine
from app.models.job_description import JobDescription
from app.models.linkedin_profile import LinkedInProfileModel

Base.metadata.create_all(bind=engine)

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


