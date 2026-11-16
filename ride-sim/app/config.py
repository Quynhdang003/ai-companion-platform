from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    # SQLite file with the quotes and bookings, relative to where the service starts. It
    # survives restarts and dev reloads; delete the file to start empty.
    database_url: str = "sqlite+aiosqlite:///./ride_sim.db"
    # Same seed and count -> the same drivers (names, vehicles, plates, positions).
    seed: int = 2026
    driver_count: int = Field(default=60, ge=0)
    # Simulated seconds per real second: at 30, a 20-minute trip ends after 40 s.
    time_scale: float = Field(default=1.0, gt=0)
    # How long a quote can still be booked, in real seconds.
    quote_ttl_seconds: int = Field(default=300, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
