import uuid
from typing import Any

import httpx
import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import CallLog, CallSession, Elder, ElderStatus
from app.services.conversation.dograh_client import (
    DograhTranscriptSource,
    TranscriptFetchError,
    UntrustedURLError,
    get_transcript_source,
)
from app.services.conversation.transcript import TranscriptFormatError, parse_dograh_transcript
from app.services.identity import call_sessions
from tests.conftest import DOGRAH_HEADERS, add_elder

RUN_ID = "42"
DOGRAH = "http://localhost:8010"
TRANSCRIPT_URL = f"{DOGRAH}/api/v1/public/download/workflow/tok/transcript"
RECORDING_URL = f"{DOGRAH}/api/v1/public/download/workflow/tok/recording"
# Same shape as a real Dograh 1.50.0 transcript file (text-chat run, 2026-11-06).
RAW_TRANSCRIPT = (
    "[2026-11-06T15:52:21.752560+00:00] assistant: Dạ, con chào bà Lan ạ.\n"
    "[2026-11-06T15:52:25.010346+00:00] user: Chào con, hôm nay trời đẹp quá.\n"
    "[2026-11-06T15:52:27.507261+00:00] assistant: Dạ vâng ạ. Bà có khỏe không ạ?\n"
)
TURNS = [
    {"role": "assistant", "text": "Dạ, con chào bà Lan ạ."},
    {"role": "elder", "text": "Chào con, hôm nay trời đẹp quá."},
    {"role": "assistant", "text": "Dạ vâng ạ. Bà có khỏe không ạ?"},
]


class FakeTranscripts:
    def __init__(self) -> None:
        self.raw = RAW_TRANSCRIPT
        self.error: Exception | None = None
        self.urls: list[str] = []

    async def fetch(self, url: str) -> str:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.raw


@pytest.fixture
def transcripts(client: AsyncClient) -> FakeTranscripts:
    fake = FakeTranscripts()
    app.dependency_overrides[get_transcript_source] = lambda: fake
    return fake


async def start_call(session: AsyncSession, elder: Elder | None) -> uuid.UUID:
    """The call session the pre-call hook opened for run RUN_ID."""
    await call_sessions.start(
        session,
        elder_id=elder.id if elder else None,
        from_number=elder.phone_e164 if elder else "+84912000009",
        workflow_run_id=RUN_ID,
    )
    return await session.scalar(select(CallSession.id).where(CallSession.workflow_run_id == RUN_ID))


async def call_ended(
    client: AsyncClient, headers: dict[str, str] = DOGRAH_HEADERS, **overrides: Any
) -> Response:
    """Body as rendered from the Webhook node's payload template: every value a string."""
    body = {
        "workflow_run_id": RUN_ID,
        "duration_seconds": "43",
        "disposition": "completed",
        "transcript_url": TRANSCRIPT_URL,
        "recording_url": RECORDING_URL,
    }
    body.update(overrides)
    return await client.post("/hooks/call-ended", json=body, headers=headers)


async def call_logs(session: AsyncSession) -> list[CallLog]:
    return list((await session.scalars(select(CallLog))).all())


async def transcript_is_sql_null(session: AsyncSession) -> bool:
    """SQL NULL, not JSON null: both load as None in Python."""
    return await session.scalar(text("SELECT transcript IS NULL FROM call_logs"))


async def test_active_caller_gets_transcript_and_recording(
    client: AsyncClient, session: AsyncSession, transcripts: FakeTranscripts
) -> None:
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    session_id = await start_call(session, elder)

    response = await call_ended(client)

    assert response.status_code == 200
    assert response.json() == {"received": True}
    [log] = await call_logs(session)
    assert log.call_session_id == session_id
    assert log.duration_seconds == 43
    assert log.disposition == "completed"
    assert log.transcript == TURNS
    assert log.recording_url == RECORDING_URL
    assert transcripts.urls == [TRANSCRIPT_URL]


async def test_caller_who_consented_during_the_call_gets_transcript(
    client: AsyncClient, session: AsyncSession, transcripts: FakeTranscripts
) -> None:
    elder = await add_elder(session, status=ElderStatus.PENDING_VERIFICATION)
    await start_call(session, elder)
    # confirm_activation ran during the call.
    await session.execute(
        update(Elder).where(Elder.id == elder.id).values(status=ElderStatus.ACTIVE)
    )

    await call_ended(client)

    [log] = await call_logs(session)
    assert log.transcript == TURNS


@pytest.mark.parametrize("status", [None, ElderStatus.PENDING_VERIFICATION, ElderStatus.BLOCKED])
async def test_caller_without_consent_gets_metadata_only(
    client: AsyncClient,
    session: AsyncSession,
    transcripts: FakeTranscripts,
    status: ElderStatus | None,
) -> None:
    elder = await add_elder(session, status=status) if status else None
    await start_call(session, elder)

    response = await call_ended(client)

    assert response.status_code == 200
    [log] = await call_logs(session)
    assert log.duration_seconds == 43
    assert await transcript_is_sql_null(session)
    assert log.recording_url is None
    assert transcripts.urls == []


async def test_retried_delivery_updates_the_same_row(
    client: AsyncClient, session: AsyncSession, transcripts: FakeTranscripts
) -> None:
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    await start_call(session, elder)
    await call_ended(client, duration_seconds="40")

    response = await call_ended(client, duration_seconds="43")

    assert response.status_code == 200
    [log] = await call_logs(session)
    assert log.duration_seconds == 43


async def test_run_without_call_session_is_ignored(
    client: AsyncClient, session: AsyncSession, transcripts: FakeTranscripts
) -> None:
    response = await call_ended(client)

    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert await call_logs(session) == []
    assert transcripts.urls == []


async def test_empty_template_values_count_as_missing(
    client: AsyncClient, session: AsyncSession, transcripts: FakeTranscripts
) -> None:
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    await start_call(session, elder)

    response = await call_ended(
        client, duration_seconds="", disposition="", transcript_url="", recording_url=" "
    )

    assert response.status_code == 200
    [log] = await call_logs(session)
    assert (log.duration_seconds, log.disposition, log.recording_url) == (None, None, None)
    assert await transcript_is_sql_null(session)
    assert transcripts.urls == []


@pytest.mark.parametrize(("sent", "stored"), [("12.6", 13), (7, 7), ("0", 0)])
async def test_duration_is_stored_in_whole_seconds(
    client: AsyncClient,
    session: AsyncSession,
    transcripts: FakeTranscripts,
    sent: Any,
    stored: int,
) -> None:
    await start_call(session, None)

    await call_ended(client, duration_seconds=sent)

    [log] = await call_logs(session)
    assert log.duration_seconds == stored


@pytest.mark.parametrize(
    "error", [TranscriptFetchError("ConnectError"), TranscriptFormatError("not a transcript")]
)
async def test_unreadable_transcript_returns_503_and_writes_nothing(
    client: AsyncClient,
    session: AsyncSession,
    transcripts: FakeTranscripts,
    error: Exception,
) -> None:
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    await start_call(session, elder)
    transcripts.error = error

    response = await call_ended(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "transcript_unavailable"
    assert await call_logs(session) == []


@pytest.mark.parametrize(
    "url", ["http://evil.test/transcript", "http://localhost:8010.evil.test/transcript"]
)
async def test_transcript_url_outside_dograh_is_rejected(
    client: AsyncClient, session: AsyncSession, url: str
) -> None:
    app.dependency_overrides[get_transcript_source] = lambda: DograhTranscriptSource(DOGRAH)
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    await start_call(session, elder)

    response = await call_ended(client, transcript_url=url)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_transcript_url"
    assert await call_logs(session) == []


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong-key"}], ids=["missing", "wrong"]
)
async def test_api_key_is_required(
    client: AsyncClient, transcripts: FakeTranscripts, headers: dict[str, str]
) -> None:
    response = await call_ended(client, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "overrides", [{"workflow_run_id": ""}, {"duration_seconds": "abc"}, {"duration_seconds": "-1"}]
)
async def test_invalid_body_is_rejected(
    client: AsyncClient, transcripts: FakeTranscripts, overrides: dict[str, Any]
) -> None:
    response = await call_ended(client, **overrides)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# Transcript parsing


def test_parses_a_dograh_transcript_file() -> None:
    assert parse_dograh_transcript(RAW_TRANSCRIPT) == TURNS


def test_multiline_message_and_missing_timestamp() -> None:
    raw = "user: dòng một\ndòng hai\n\n[t] assistant: ừ\n[t] user:   \n"

    assert parse_dograh_transcript(raw) == [
        {"role": "elder", "text": "dòng một\ndòng hai"},
        {"role": "assistant", "text": "ừ"},
    ]


def test_empty_transcript_has_no_turns() -> None:
    assert parse_dograh_transcript("") == []


def test_text_before_the_first_message_is_rejected() -> None:
    with pytest.raises(TranscriptFormatError):
        parse_dograh_transcript("<html>Not found</html>\n[t] user: hi\n")


# Downloading from Dograh


def dograh_storage(request: httpx.Request) -> httpx.Response:
    """Dograh's public download route redirects to signed MinIO storage."""
    if request.url.host == "localhost" and request.url.port == 8010:
        return httpx.Response(302, headers={"location": "http://localhost:9000/t/42.txt?sig=x"})
    if request.url.path == "/t/42.txt":
        return httpx.Response(200, content=RAW_TRANSCRIPT.encode())
    return httpx.Response(404)


async def test_download_follows_the_redirect_to_storage() -> None:
    source = DograhTranscriptSource(DOGRAH, transport=httpx.MockTransport(dograh_storage))

    assert await source.fetch(TRANSCRIPT_URL) == RAW_TRANSCRIPT


async def test_download_error_is_retryable() -> None:
    source = DograhTranscriptSource(
        DOGRAH, transport=httpx.MockTransport(lambda _: httpx.Response(404))
    )

    with pytest.raises(TranscriptFetchError):
        await source.fetch(TRANSCRIPT_URL)


async def test_download_only_from_dograh() -> None:
    source = DograhTranscriptSource(DOGRAH + "/")

    with pytest.raises(UntrustedURLError):
        await source.fetch("http://localhost:9000/t/42.txt")
