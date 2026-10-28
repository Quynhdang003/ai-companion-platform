from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    # Local-dev default matches infra/docker-compose.yml; override via DATABASE_URL.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_companion"
    # Dropped and recreated by the test suite; must be a separate database.
    test_database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_companion_test"
    )

    # Clerk Frontend API URL, e.g. https://xxx.clerk.accounts.dev (JWT `iss`, JWKS host).
    clerk_issuer: str = ""
    # Origins allowed as the JWT `azp` claim.
    clerk_authorized_parties: list[str] = ["http://localhost:3000"]
    # Svix signing secret of the Clerk webhook endpoint (whsec_...).
    clerk_webhook_secret: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
