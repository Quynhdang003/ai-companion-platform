"""Per-call sessions: the session_token Dograh tools send so the backend knows the caller."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import CallSession


class InvalidSessionError(Exception):
    """Unknown or expired session token (indistinguishable on purpose)."""


def hash_token(token: str) -> str:
    # Tokens are 256 random bits, so a fast unsalted hash is safe and allows lookup by hash.
    return hashlib.sha256(token.encode()).hexdigest()


async def start(
    db: AsyncSession,
    *,
    elder_id: uuid.UUID | None,
    from_number: str,
    workflow_run_id: str | None,
) -> str:
    """Open a session for a call and return its token; only the hash is stored."""
    token = secrets.token_urlsafe(32)
    ttl = timedelta(minutes=get_settings().session_token_ttl_minutes)
    values = {
        "elder_id": elder_id,
        "session_token_hash": hash_token(token),
        "from_number": from_number,
        "expires_at": datetime.now(UTC) + ttl,
    }
    # Dograh retries a hook it got no answer for: rotate the token on that run's session,
    # so only the token in the response Dograh actually received works.
    await db.execute(
        insert(CallSession)
        .values(workflow_run_id=workflow_run_id, **values)
        .on_conflict_do_update(index_elements=[CallSession.workflow_run_id], set_=values)
    )
    return token


async def resolve(db: AsyncSession, token: str) -> CallSession:
    call = await db.scalar(
        select(CallSession).where(
            CallSession.session_token_hash == hash_token(token),
            CallSession.expires_at > datetime.now(UTC),
        )
    )
    if call is None:
        raise InvalidSessionError
    return call
