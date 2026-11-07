"""Background job: extract memories from stored call transcripts.

Runs from the scheduler (`app/core/scheduler.py`), never inside the end-of-call webhook
(architecture invariant 4). A call log is claimed with `FOR UPDATE SKIP LOCKED`, so two
workers never process the same one. Logs never contain transcript or memory text.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import timedelta, timezone

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.llm.client import (
    LLMClient,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitedError,
    get_llm_client,
)
from app.models import CallLog, CallSession, Elder, ElderStatus, MemoryStatus
from app.services.memory.extraction import extract_call_memories

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BATCH_SIZE = 5
# Relative dates in a call ("tuần sau") are resolved against the Vietnamese calendar date.
VN_TZ = timezone(timedelta(hours=7))

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def process_next(db: AsyncSession, llm: LLMClient) -> bool:
    """Process the oldest pending call log; False when none is left.

    Raises `LLMRateLimitedError` / `LLMNotConfiguredError` with the log still pending and
    its attempts unchanged, so the caller stops instead of burning attempts.
    """
    log = await db.scalar(
        select(CallLog)
        .where(CallLog.memory_status == MemoryStatus.PENDING)
        .order_by(CallLog.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if log is None:
        return False

    caller = (
        await db.execute(
            select(Elder.id, Elder.status, CallSession.started_at)
            .join(Elder, Elder.id == CallSession.elder_id)
            .where(CallSession.id == log.call_session_id)
        )
    ).first()
    if not log.transcript or caller is None or caller.status is not ElderStatus.ACTIVE:
        log.memory_status = MemoryStatus.SKIPPED
        await db.commit()
        return True

    log_id = log.id
    try:
        async with db.begin_nested():
            result = await extract_call_memories(
                db, llm, log, caller.id, caller.started_at.astimezone(VN_TZ).date()
            )
    except (LLMRateLimitedError, LLMNotConfiguredError):
        await db.rollback()
        raise
    except LLMError as exc:
        attempts = await db.scalar(
            update(CallLog)
            .where(CallLog.id == log_id)
            .values(
                memory_attempts=CallLog.memory_attempts + 1,
                memory_status=case(
                    (CallLog.memory_attempts + 1 >= MAX_ATTEMPTS, MemoryStatus.FAILED.value),
                    else_=MemoryStatus.PENDING.value,
                ),
            )
            .returning(CallLog.memory_attempts)
        )
        await db.commit()
        logger.warning(
            "memory extraction failed for call log %s (attempt %s/%s): %s",
            log_id,
            attempts,
            MAX_ATTEMPTS,
            exc,
        )
        return True

    log.memory_status = MemoryStatus.DONE
    await db.commit()
    logger.info(
        "memories from call log %s: %d added, %d updated", log_id, result.added, result.updated
    )
    return True


async def run_memory_job(
    session_factory: SessionFactory = SessionLocal,
    llm: LLMClient | None = None,
    batch_size: int = BATCH_SIZE,
) -> int:
    """One scheduler run: up to `batch_size` call logs. Returns how many were processed."""
    llm = llm or get_llm_client()
    processed = 0
    async with session_factory() as db:
        try:
            while processed < batch_size and await process_next(db, llm):
                processed += 1
        except (LLMRateLimitedError, LLMNotConfiguredError) as exc:
            logger.info("memory job paused until its next run: %s", type(exc).__name__)
    return processed
