"""The caller of a Dograh tool, from its `session_token` (never from the LLM)."""

from app.core.db import DbSession
from app.core.errors import AppError
from app.models import CallSession
from app.services.identity import call_sessions
from app.services.identity.call_sessions import InvalidSessionError


async def resolve_call(db: DbSession, token: str) -> CallSession:
    try:
        return await call_sessions.resolve(db, token)
    except InvalidSessionError as exc:
        raise AppError(401, "invalid_session", "Phiên gọi đã hết hạn, vui lòng gọi lại.") from exc
