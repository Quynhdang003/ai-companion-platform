from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dograh import hooks, tools
from app.api.web import elders, link_requests, me
from app.api.webhooks import clerk
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    scheduler = start_scheduler(get_settings())
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title="AI Companion Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
register_error_handlers(app)

app.include_router(me.router)
app.include_router(elders.router)
app.include_router(link_requests.router)
app.include_router(clerk.router)
app.include_router(hooks.router)
app.include_router(tools.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
