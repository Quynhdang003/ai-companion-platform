import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import CallSession
from app.services.identity import call_sessions
from app.services.identity.call_sessions import InvalidSessionError


async def start(session: AsyncSession, workflow_run_id: str | None = "101") -> str:
    return await call_sessions.start(
        session, elder_id=None, from_number="+84912345678", workflow_run_id=workflow_run_id
    )


async def count_sessions(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(CallSession))


async def test_start_stores_only_the_token_hash(session: AsyncSession) -> None:
    token = await start(session)

    call = await session.scalar(select(CallSession))
    assert call is not None
    assert call.session_token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert call.session_token_hash != token
    assert len(token) >= 43  # 32 random bytes, URL-safe base64
    ttl = timedelta(minutes=get_settings().session_token_ttl_minutes)
    assert call.expires_at > datetime.now(UTC) + ttl - timedelta(minutes=1)


async def test_resolve_returns_the_session_of_a_valid_token(session: AsyncSession) -> None:
    token = await start(session)

    call = await call_sessions.resolve(session, token)

    assert call.workflow_run_id == "101"


async def test_resolve_rejects_unknown_token(session: AsyncSession) -> None:
    await start(session)

    with pytest.raises(InvalidSessionError):
        await call_sessions.resolve(session, "not-a-real-token")


async def test_resolve_rejects_expired_token(session: AsyncSession) -> None:
    token = await start(session)
    await session.execute(
        update(CallSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )

    with pytest.raises(InvalidSessionError):
        await call_sessions.resolve(session, token)


async def test_retry_for_same_run_rotates_token_on_one_session(session: AsyncSession) -> None:
    old = await start(session, workflow_run_id="7")
    new = await start(session, workflow_run_id="7")

    assert await count_sessions(session) == 1
    assert (await call_sessions.resolve(session, new)).workflow_run_id == "7"
    with pytest.raises(InvalidSessionError):
        await call_sessions.resolve(session, old)


async def test_sessions_without_run_id_never_collide(session: AsyncSession) -> None:
    await start(session, workflow_run_id=None)
    await start(session, workflow_run_id=None)

    assert await count_sessions(session) == 2
