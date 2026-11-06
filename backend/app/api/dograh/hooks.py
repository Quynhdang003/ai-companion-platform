from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.db import DbSession
from app.core.dograh_auth import require_dograh_key
from app.core.errors import AppError
from app.schemas.dograh import CallEndedOut, CallEndedRequest, PreCallRequest, PreCallResponse
from app.services.conversation import call_logs
from app.services.conversation.dograh_client import (
    TranscriptFetchError,
    TranscriptSource,
    UntrustedURLError,
    get_transcript_source,
)
from app.services.conversation.transcript import TranscriptFormatError
from app.services.identity import pre_call

router = APIRouter(prefix="/hooks", tags=["dograh"], dependencies=[Depends(require_dograh_key)])


@router.post("/pre-call", response_model=PreCallResponse, response_model_exclude_none=True)
async def pre_call_hook(body: PreCallRequest, db: DbSession) -> PreCallResponse:
    """Dograh calls this before the agent speaks; the response merges into `initial_context`."""
    context = await pre_call.build_context(db, body.call_inbound)
    await db.commit()
    return PreCallResponse(initial_context=context)


@router.post("/call-ended", response_model=CallEndedOut)
async def call_ended_hook(
    body: CallEndedRequest,
    db: DbSession,
    transcripts: Annotated[TranscriptSource, Depends(get_transcript_source)],
) -> CallEndedOut:
    """Dograh's end-of-call Webhook node. A 503 makes Dograh retry the delivery later."""
    try:
        await call_logs.record_call_end(db, body, transcripts)
    except UntrustedURLError as exc:
        raise AppError(
            422, "invalid_transcript_url", "transcript_url is not a Dograh download link"
        ) from exc
    except (TranscriptFetchError, TranscriptFormatError) as exc:
        raise AppError(
            503, "transcript_unavailable", "Transcript could not be read, retry later"
        ) from exc
    await db.commit()
    return CallEndedOut()
