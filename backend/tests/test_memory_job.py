import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.scheduler import start_scheduler
from app.llm.client import LLMError, LLMNotConfiguredError, LLMRateLimitedError
from app.models import (
    CallLog,
    CallSession,
    Elder,
    ElderStatus,
    Memory,
    MemoryCategory,
    MemoryStatus,
)
from app.services.memory.job import MAX_ATTEMPTS, SessionFactory, process_next, run_memory_job
from tests.conftest import add_elder
from tests.fakes import FakeLLMClient, fake_vector

TURNS = [
    {"role": "assistant", "text": "Dạ, con chào bà Lan ạ."},
    {"role": "elder", "text": "Tuần sau bà đi khám ở Bệnh viện Bạch Mai."},
]
# 06:30 on 7 November in Vietnam (UTC+7).
CALL_START = datetime(2026, 11, 6, 23, 30, tzinfo=UTC)
BACH_MAI = "Bà hay đi khám ở Bệnh viện Bạch Mai."


def add(content: str, **fields: Any) -> dict[str, Any]:
    return {"action": "add", "ref": None, "category": "place", "importance": 3, **fields} | {
        "content": content
    }


def update(ref: str, content: str, **fields: Any) -> dict[str, Any]:
    return {"action": "update", "ref": ref, "category": "place", "importance": 3, **fields} | {
        "content": content
    }


async def add_call_log(
    session: AsyncSession,
    elder: Elder | None,
    *,
    transcript: list[dict[str, str]] | None = TURNS,
    status: MemoryStatus = MemoryStatus.PENDING,
) -> CallLog:
    call = CallSession(
        elder_id=elder.id if elder else None,
        session_token_hash=uuid.uuid4().hex,
        workflow_run_id=uuid.uuid4().hex[:12],
        from_number=elder.phone_e164 if elder else "+84912000009",
        started_at=CALL_START,
        expires_at=CALL_START + timedelta(hours=2),
    )
    session.add(call)
    await session.flush()
    log = CallLog(call_session_id=call.id, transcript=transcript, memory_status=status)
    session.add(log)
    await session.flush()
    return log


async def add_memory(
    session: AsyncSession, elder: Elder, content: str, subject: str | None = None
) -> Memory:
    memory = Memory(
        elder_id=elder.id,
        category=MemoryCategory.PLACE,
        subject=subject,
        content=content,
        importance=3,
        embedding=fake_vector(content),
    )
    session.add(memory)
    await session.flush()
    return memory


async def memories_of(session: AsyncSession, elder: Elder) -> list[Memory]:
    rows = await session.scalars(
        select(Memory).where(Memory.elder_id == elder.id).order_by(Memory.content)
    )
    return list(rows.all())


async def reload(session: AsyncSession, log: CallLog) -> CallLog:
    # The identity key needs no IO, even when a rollback expired the object.
    [log_id] = inspect(log).identity
    return await session.scalar(
        select(CallLog).where(CallLog.id == log_id).execution_options(populate_existing=True)
    )


def same_session(session: AsyncSession) -> SessionFactory:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
async def elder(session: AsyncSession) -> Elder:
    return await add_elder(session, status=ElderStatus.ACTIVE)


async def test_new_facts_become_embedded_memories(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    log = await add_call_log(session, elder)
    await session.commit()
    llm.replies.append(
        {
            "memories": [
                add(BACH_MAI, subject="Bệnh viện Bạch Mai", importance=4),
                add("Bà thích nghe cải lương.", category="preference", importance=2),
            ]
        }
    )

    assert await process_next(session, llm) is True

    hospital, music = await memories_of(session, elder)
    assert (hospital.category, hospital.subject, hospital.importance) == (
        MemoryCategory.PLACE,
        "Bệnh viện Bạch Mai",
        4,
    )
    assert music.category is MemoryCategory.PREFERENCE and music.subject is None
    assert hospital.mention_count == 1 and hospital.source_call_log_id == log.id
    expected_text = f"Bệnh viện Bạch Mai: {BACH_MAI}"
    assert llm.embedded == [([expected_text, "Bà thích nghe cải lương."], "document")]
    assert list(hospital.embedding) == pytest.approx(fake_vector(expected_text), abs=1e-6)
    log = await reload(session, log)
    assert (log.memory_status, log.memory_attempts) == (MemoryStatus.DONE, 0)


async def test_prompt_has_the_call_date_transcript_and_no_memories_yet(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    await add_call_log(session, elder)
    await session.commit()
    llm.replies.append({"memories": []})

    await process_next(session, llm)

    [prompt] = llm.prompts
    assert "Call date: 2026-11-07" in prompt
    assert "Existing memories:\n(none)" in prompt
    assert "Người cao tuổi: Tuần sau bà đi khám ở Bệnh viện Bạch Mai." in prompt
    assert "Trợ lý: Dạ, con chào bà Lan ạ." in prompt


async def test_repeated_fact_updates_the_existing_memory(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    old = await add_memory(session, elder, BACH_MAI, subject="Bệnh viện Bạch Mai")
    await add_call_log(session, elder)
    await session.commit()
    new_content = "Bà đi khám ở Bệnh viện Bạch Mai vào sáng thứ Ba."
    llm.replies.append({"memories": [update("m1", new_content, subject="Bệnh viện Bạch Mai")]})

    await process_next(session, llm)

    assert f"- m1 [place] Bệnh viện Bạch Mai: {BACH_MAI}" in llm.prompts[0]
    [memory] = await memories_of(session, elder)
    assert memory.id == old.id
    assert memory.content == new_content and memory.mention_count == 2
    assert list(memory.embedding) == pytest.approx(
        fake_vector(f"Bệnh viện Bạch Mai: {new_content}"), abs=1e-6
    )


async def test_unknown_ref_is_added_and_the_last_update_wins(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    await add_memory(session, elder, BACH_MAI)
    await add_call_log(session, elder)
    await session.commit()
    llm.replies.append(
        {
            "memories": [
                update("m7", "Bà có con gái tên Mai.", category="person"),
                update("m1", "Bà khám ở Bạch Mai."),
                update("m1", "Bà khám ở Bạch Mai thứ Ba."),
            ]
        }
    )

    await process_next(session, llm)

    daughter, hospital = await memories_of(session, elder)
    assert hospital.content == "Bà khám ở Bạch Mai thứ Ba." and hospital.mention_count == 2
    assert daughter.category is MemoryCategory.PERSON and daughter.mention_count == 1


async def test_prompt_shows_only_this_elders_memories(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    other = await add_elder(session, status=ElderStatus.ACTIVE, phone_e164="+84912000111")
    await add_memory(session, other, "Ông thích chơi cờ tướng.")
    await add_call_log(session, elder)
    await session.commit()
    llm.replies.append({"memories": []})

    await process_next(session, llm)

    assert "cờ tướng" not in llm.prompts[0]


async def test_invalid_output_writes_nothing_and_fails_after_max_attempts(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    await add_memory(session, elder, BACH_MAI)
    log = await add_call_log(session, elder)
    await session.commit()
    llm.replies += ['{"memories": [{"action": "add"}]}'] * MAX_ATTEMPTS

    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert await process_next(session, llm) is True
        log = await reload(session, log)
        assert log.memory_attempts == attempt

    assert log.memory_status is MemoryStatus.FAILED
    assert await process_next(session, llm) is False
    [memory] = await memories_of(session, elder)
    assert memory.content == BACH_MAI and memory.mention_count == 1


async def test_embedding_failure_writes_nothing(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    await add_memory(session, elder, BACH_MAI)
    log = await add_call_log(session, elder)
    await session.commit()
    llm.replies.append({"memories": [update("m1", "Đổi nội dung."), add("Mới.")]})
    llm.embed_error = LLMError("down")

    await process_next(session, llm)

    [memory] = await memories_of(session, elder)
    assert memory.content == BACH_MAI
    log = await reload(session, log)
    assert (log.memory_status, log.memory_attempts) == (MemoryStatus.PENDING, 1)


@pytest.mark.parametrize("error", [LLMRateLimitedError("quota"), LLMNotConfiguredError("key")])
async def test_rate_limit_or_missing_key_leaves_the_log_untouched(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient, error: LLMError
) -> None:
    log = await add_call_log(session, elder)
    await session.commit()
    llm.replies.append(error)

    with pytest.raises(type(error)):
        await process_next(session, llm)

    log = await reload(session, log)
    assert (log.memory_status, log.memory_attempts) == (MemoryStatus.PENDING, 0)


@pytest.mark.parametrize(
    ("status", "transcript"),
    [(ElderStatus.BLOCKED, TURNS), (ElderStatus.PENDING_VERIFICATION, TURNS), (None, TURNS)]
    + [(ElderStatus.ACTIVE, []), (ElderStatus.ACTIVE, None)],
)
async def test_logs_without_consent_or_content_are_skipped(
    session: AsyncSession,
    llm: FakeLLMClient,
    status: ElderStatus | None,
    transcript: list[dict[str, str]] | None,
) -> None:
    elder = await add_elder(session, status=status) if status else None
    log = await add_call_log(session, elder, transcript=transcript)
    await session.commit()

    assert await process_next(session, llm) is True

    assert (await reload(session, log)).memory_status is MemoryStatus.SKIPPED
    assert llm.prompts == []


async def test_nothing_pending(session: AsyncSession, elder: Elder, llm: FakeLLMClient) -> None:
    await add_call_log(session, elder, status=MemoryStatus.DONE)
    await session.commit()

    assert await process_next(session, llm) is False


async def test_job_run_handles_at_most_a_batch(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    for _ in range(3):
        await add_call_log(session, elder)
    await session.commit()
    llm.replies += [{"memories": []}] * 3

    assert await run_memory_job(same_session(session), llm, batch_size=2) == 2

    statuses = (await session.scalars(select(CallLog.memory_status))).all()
    assert sorted(statuses) == [MemoryStatus.DONE, MemoryStatus.DONE, MemoryStatus.PENDING]


async def test_job_run_stops_when_rate_limited(
    session: AsyncSession, elder: Elder, llm: FakeLLMClient
) -> None:
    for _ in range(2):
        await add_call_log(session, elder)
    await session.commit()
    llm.replies.append(LLMRateLimitedError("quota"))

    assert await run_memory_job(same_session(session), llm) == 0

    assert len(llm.prompts) == 1
    statuses = (await session.scalars(select(CallLog.memory_status))).all()
    assert statuses == [MemoryStatus.PENDING, MemoryStatus.PENDING]


async def test_scheduler_runs_memory_job_only_with_a_gemini_key() -> None:
    assert start_scheduler(Settings(scheduler_enabled=False)) is None

    without_key = start_scheduler(Settings(scheduler_enabled=True, gemini_api_key=""))
    with_key = start_scheduler(Settings(scheduler_enabled=True, gemini_api_key="k"))
    try:
        assert without_key is not None and without_key.get_job("memory_extraction") is None
        assert with_key is not None and with_key.get_job("memory_extraction") is not None
    finally:
        for scheduler in (without_key, with_key):
            if scheduler is not None:
                scheduler.shutdown(wait=False)
