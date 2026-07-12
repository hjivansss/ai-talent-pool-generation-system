from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Talent Pool Search"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:3b"

    DATABASE_URL: str 
    
    GITHUB_TOKEN: str | None = None

    #calling enabled for CORS in the frontend, so that the frontend can make requests to the backend 
    # without being blocked by the browser's same-origin policy.
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()