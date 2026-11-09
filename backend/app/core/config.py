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

    # Shared secret Dograh sends as `Authorization: Bearer ...` on hooks and tools.
    dograh_api_key: str = ""
    # Lifetime of a call's session_token; tools reject it afterwards.
    session_token_ttl_minutes: int = 120
    # Dograh API origin as seen from the backend (Dograh's BACKEND_API_ENDPOINT). The backend
    # downloads transcripts only from links under it.
    dograh_base_url: str = "http://localhost:8010"

    # Gemini (Google AI Studio) for analysis (memory extraction, scam) and embeddings. Calls
    # themselves use Dograh's own models. Unset key: LLM calls fail with LLMNotConfiguredError.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    llm_timeout_seconds: float = 30.0

    # Background jobs (APScheduler, started with the app). Tests never start them.
    scheduler_enabled: bool = True
    memory_job_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
