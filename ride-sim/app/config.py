from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Fault(StrEnum):
    """A failure the simulator plays on purpose; one at a time (`/sim/config`)."""

    NO_DRIVER = "no_driver"  # booking finds no driver
    DRIVER_CANCELS = "driver_cancels"  # the driver accepts, then cancels
    TIMEOUT = "timeout"  # requests hang, then fail
    PRICE_SURGE = "price_surge"  # new quotes cost more


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
    # Changeable while running (`PATCH /sim/config`); this is the value at start.
    time_scale: float = Field(default=1.0, gt=0)
    # How long a quote can still be booked, in real seconds.
    quote_ttl_seconds: int = Field(default=300, gt=0)

    # Road routes from an OSRM server. Empty: straight-line estimates only, no network.
    osrm_base_url: str = "https://router.project-osrm.org"
    router_timeout_seconds: float = Field(default=2.0, gt=0)
    # Place search on a Photon server. Empty: the built-in Hanoi places only.
    photon_base_url: str = "https://photon.komoot.io"
    # Public Photon took 3-6 s from Vietnam (2026-11-16); a self-hosted one answers far faster.
    geocoder_timeout_seconds: float = Field(default=6.0, gt=0)

    # Fault active from the start (also changeable while running); empty = none.
    fault: Fault | None = None
    # Under the `timeout` fault, a request hangs this long (real seconds), then fails.
    fault_timeout_seconds: float = Field(default=15.0, ge=0)
    # Under the `price_surge` fault, new quotes are multiplied by this.
    surge_multiplier: float = Field(default=1.8, ge=1)

    @field_validator("fault", mode="before")
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
