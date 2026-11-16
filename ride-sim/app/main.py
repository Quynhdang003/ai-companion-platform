import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import routes
from app.config import Settings, get_settings
from app.db import prepare_database
from app.errors import register_error_handlers
from app.geocoding import BuiltinPlaces, Geocoder, PhotonGeocoder, PlaceSearch
from app.routing import OsrmRouter, Router, StraightLineRouter
from app.simulator import Clock, Simulator, Sleep, utc_now

# Sent to the public map servers: says what is calling, nothing about who.
USER_AGENT = "ride-sim/0.1"


def create_app(
    settings: Settings | None = None,
    *,
    router: Router | None = None,
    geocoder: Geocoder | None = None,
    clock: Clock = utc_now,
    sleep: Sleep = asyncio.sleep,
) -> FastAPI:
    """Tests pass their own settings (a throwaway database, no map servers), router,
    geocoder, clock and sleep. Left out, the router and the geocoder come from the settings.
    """
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url)
        await prepare_database(engine)
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as http:
            app.state.simulator = Simulator(
                settings,
                async_sessionmaker(engine, expire_on_commit=False),
                router or _router(settings, http),
                clock,
                sleep,
            )
            app.state.places = PlaceSearch(
                BuiltinPlaces.load(), geocoder or _geocoder(settings, http)
            )
            try:
                yield
            finally:
                await engine.dispose()

    app = FastAPI(title="Ride Simulator", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(routes.router)
    app.include_router(routes.sim_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _router(settings: Settings, http: httpx.AsyncClient) -> Router:
    if not settings.osrm_base_url:
        return StraightLineRouter()
    return OsrmRouter(http, settings.osrm_base_url, settings.router_timeout_seconds)


def _geocoder(settings: Settings, http: httpx.AsyncClient) -> Geocoder | None:
    if not settings.photon_base_url:
        return None
    return PhotonGeocoder(http, settings.photon_base_url, settings.geocoder_timeout_seconds)


app = create_app()
