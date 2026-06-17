from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Talent Pool Search"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:3b"

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_talent_pool_search"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()