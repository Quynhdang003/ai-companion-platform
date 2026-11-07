"""End of a call: store what happened, linked to the call's session by Dograh's run id."""

import logging

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallLog, CallSession, Elder, ElderStatus, MemoryStatus
from app.schemas.dograh import CallEndedRequest
from app.services.conversation.dograh_client import TranscriptSource
from app.services.conversation.transcript import parse_dograh_transcript

logger = logging.getLogger(__name__)


async def record_call_end(
    db: AsyncSession, call: CallEndedRequest, transcripts: TranscriptSource
) -> CallLog | None:
    """Upsert the call's log; None if the run has no session (its pre-call hook never reached
    us). Content (transcript, recording link) is kept only if the caller has consented.

    Raises `TranscriptFetchError`, `UntrustedURLError` or `TranscriptFormatError` before
    writing anything, so a retried webhook starts clean.
    """
    session = await db.scalar(
        select(CallSession).where(CallSession.workflow_run_id == call.workflow_run_id)
    )
    if session is None:
        logger.info("call-ended for run %s without a call session; ignored", call.workflow_run_id)
        return None

    transcript = recording_url = None
    if await _has_consented(db, session):
        if call.transcript_url:
            transcript = parse_dograh_transcript(await transcripts.fetch(call.transcript_url))
        recording_url = call.recording_url

    values = {
        "duration_seconds": call.duration_seconds,
        "disposition": call.disposition,
        "transcript": transcript,
        "recording_url": recording_url,
    }
    # A transcript queues the post-call memory extraction (app/services/memory/job.py).
    memory_status = MemoryStatus.PENDING if transcript else MemoryStatus.SKIPPED
    stmt = insert(CallLog).values(call_session_id=session.id, memory_status=memory_status, **values)
    # Dograh retries deliveries: a repeat overwrites the same row, but an extraction that is
    # queued, done or failed keeps its state.
    return await db.scalar(
        stmt.on_conflict_do_update(
            index_elements=[CallLog.call_session_id],
            set_={
                **values,
                "memory_status": case(
                    (
                        CallLog.memory_status == MemoryStatus.SKIPPED.value,
                        stmt.excluded.memory_status,
                    ),
                    else_=CallLog.memory_status,
                ),
                "updated_at": func.now(),
            },
        )
        .returning(CallLog)
        .execution_options(populate_existing=True)
    )


async def _has_consented(db: AsyncSession, session: CallSession) -> bool:
    """ACTIVE at the end of the call, including callers who consented during it."""
    if session.elder_id is None:
        return False
    status = await db.scalar(select(Elder.status).where(Elder.id == session.elder_id))
    return status is ElderStatus.ACTIVE
