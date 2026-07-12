from fastapi import FastAPI

from app.core.config import settings
from app.api.router import router as api_router 

from app.core.database import Base, engine , SessionLocal
from app.models.job_description import JobDescription
from app.models.linkedin_profile import LinkedInProfileModel
from app.models.resume import ResumeModel
from app.models.talent_pool import TalentPool
from app.services import vector_store
from fastapi.middleware.cors import CORSMiddleware

Base.metadata.create_all(bind=engine)

# Ensure pgvector embedding tables exist
db = SessionLocal()
try:
    vector_store.ensure_tables(db)
finally:
    db.close()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered talent pool search and candidate ranking backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
