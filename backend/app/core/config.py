from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    # Local-dev default matches infra/docker-compose.yml; override via DATABASE_URL.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_companion"


@lru_cache
def get_settings() -> Settings:
    return Settings()
