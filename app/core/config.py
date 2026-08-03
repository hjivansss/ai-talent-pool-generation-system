from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Talent Pool Search"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:3b"
    # Keeps the model resident in Ollama's memory between requests so we don't pay a ~60-70s cold-load tax on the first call of every run (measured on
    # 2026-07-18: first eval call was 97s vs ~35s steady-state, same prompt size).
    OLLAMA_KEEP_ALIVE: str = "30m"
    # Hard cap on generated tokens per Stage-2 evaluation call. Generation is
    # the dominant cost on CPU-only hardware (measured: ~35s/candidate on an
    # i3-1115G4) — capping output length is the single biggest lever we have
    # on that hardware, more effective than trimming the prompt.
    OLLAMA_NUM_PREDICT: int = 180

    # Stage 2 (Ollama) tuning — see evaluation_service.py
    MAX_EVALUATED: int = 5          # candidates considered for the final pool
    # Candidates below this composite Stage-1 score don't get an Ollama call at
    # all — their evaluation is generated directly from Stage-1 data (see
    # evaluation_service._template_evaluation). Weak candidates rarely need an
    # LLM to tell you they're missing most of the required skills; measured
    # run 2026-07-18 spent 154s of 311s evaluating 4 candidates who all scored
    # "Partial Match"/"Not Recommended" — that's compute worth skipping.
    LLM_SCORE_THRESHOLD: float = 0.35

    DATABASE_URL: str 
    
    GITHUB_TOKEN: str | None = None

    # Cloudinary — stores the raw uploaded resume file so recruiters can view
    # the original document, not just the parsed data
    CLOUDINARY_CLOUD_NAME: str | None = None
    CLOUDINARY_API_KEY: str | None = None
    CLOUDINARY_API_SECRET: str | None = None

    # Auth — see app/core/security.py and app/services/auth_service.py.
    JWT_SECRET_KEY: str 
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours


    #calling enabled for CORS in the frontend, so that the frontend can make requests to the backend 
    # without being blocked by the browser's same-origin policy.
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()