from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.web import me
from app.api.webhooks import clerk
from app.core.config import get_settings
from app.core.errors import register_error_handlers

app = FastAPI(title="AI Companion Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
register_error_handlers(app)

app.include_router(me.router)
app.include_router(clerk.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
