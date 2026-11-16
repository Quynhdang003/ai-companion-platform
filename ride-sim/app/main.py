from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import routes
from app.config import Settings, get_settings
from app.db import create_tables
from app.errors import register_error_handlers
from app.routing import Router, StraightLineRouter
from app.simulator import Clock, Simulator, utc_now


def create_app(
    settings: Settings | None = None, *, router: Router | None = None, clock: Clock = utc_now
) -> FastAPI:
    """Tests pass their own settings (a throwaway database), router and clock."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url)
        await create_tables(engine)
        app.state.simulator = Simulator(
            settings,
            async_sessionmaker(engine, expire_on_commit=False),
            router or StraightLineRouter(),
            clock,
        )
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Ride Simulator", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(routes.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
