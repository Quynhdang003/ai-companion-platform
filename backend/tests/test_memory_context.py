from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, ElderStatus, MemoryCategory
from app.services.memory.context import (
    PLACES_LIMIT,
    SUMMARY_LIMIT,
    SUMMARY_MAX_CHARS,
    memory_context,
)
from tests.conftest import add_elder, add_memory
from tests.test_pre_call_hook import context_of, pre_call

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


@pytest.fixture
async def elder(session: AsyncSession) -> Elder:
    return await add_elder(session, status=ElderStatus.ACTIVE)


async def add_fact(session: AsyncSession, elder: Elder, content: str, **fields: object) -> None:
    await add_memory(
        session, elder, content, category=fields.pop("category", MemoryCategory.PERSON), **fields
    )


async def test_summary_puts_important_then_recent_facts_first(
    session: AsyncSession, elder: Elder
) -> None:
    await add_fact(session, elder, "Bà thích nghe cải lương", importance=2)
    await add_fact(session, elder, "Bà bị huyết áp cao.", importance=5, last_mentioned_at=NOW)
    await add_fact(
        session,
        elder,
        "Bà có con gái tên Mai.",
        importance=5,
        last_mentioned_at=NOW - timedelta(days=3),
    )

    context = await memory_context(session, elder.id)

    assert context.summary == (
        "Bà bị huyết áp cao. Bà có con gái tên Mai. Bà thích nghe cải lương."
    )


async def test_summary_keeps_whole_sentences_within_the_limits(
    session: AsyncSession, elder: Elder
) -> None:
    for i in range(SUMMARY_LIMIT + 2):
        await add_fact(session, elder, f"Câu số {i:02d} " + "x" * 90 + ".", importance=3)

    summary = (await memory_context(session, elder.id)).summary

    assert summary is not None and len(summary) <= SUMMARY_MAX_CHARS
    sentences = summary.split(". ")
    assert 1 < len(sentences) <= SUMMARY_LIMIT
    assert summary.endswith(".")


async def test_places_are_listed_by_mentions_and_kept_out_of_the_summary(
    session: AsyncSession, elder: Elder
) -> None:
    await add_memory(session, elder, "Bà hay đi khám ở đây.", "Bệnh viện Bạch Mai", mention_count=4)
    await add_memory(session, elder, "Nhà bà ở số 12 ngõ 34 Kim Mã.", "Nhà", mention_count=7)
    await add_memory(session, elder, "Chùa gần nhà bà.", mention_count=1)

    context = await memory_context(session, elder.id)

    assert context.frequent_places == (
        "Nhà: Nhà bà ở số 12 ngõ 34 Kim Mã.; "
        "Bệnh viện Bạch Mai: Bà hay đi khám ở đây.; "
        "Chùa gần nhà bà."
    )
    assert context.summary is None


async def test_places_are_capped(session: AsyncSession, elder: Elder) -> None:
    for i in range(PLACES_LIMIT + 3):
        await add_memory(session, elder, f"Nơi {i}.", f"Nơi {i}", mention_count=i)

    places = (await memory_context(session, elder.id)).frequent_places

    assert places is not None and places.count(";") == PLACES_LIMIT - 1
    assert places.startswith(f"Nơi {PLACES_LIMIT + 2}:")


async def test_other_elders_memories_never_leak(session: AsyncSession, elder: Elder) -> None:
    other = await add_elder(session, status=ElderStatus.ACTIVE, phone_e164="+84912000111")
    await add_fact(session, other, "Ông thích chơi cờ tướng.")
    await add_memory(session, other, "Ông hay ra Hồ Gươm.", "Hồ Gươm")

    context = await memory_context(session, elder.id)

    assert (context.summary, context.frequent_places) == (None, None)


async def test_active_caller_gets_memory_keys_in_initial_context(
    client: AsyncClient, session: AsyncSession, elder: Elder
) -> None:
    await add_fact(session, elder, "Bà có con gái tên Mai.")
    await add_memory(session, elder, "Bà hay đi khám ở đây.", "Bệnh viện Bạch Mai")

    context = context_of(await pre_call(client))

    assert context["memory_summary"] == "Bà có con gái tên Mai."
    assert context["frequent_places"] == "Bệnh viện Bạch Mai: Bà hay đi khám ở đây."


async def test_active_caller_without_memories_gets_no_memory_keys(
    client: AsyncClient, session: AsyncSession, elder: Elder
) -> None:
    context = context_of(await pre_call(client))

    assert "memory_summary" not in context and "frequent_places" not in context


@pytest.mark.parametrize("status", [ElderStatus.PENDING_VERIFICATION, ElderStatus.BLOCKED])
async def test_callers_without_consent_never_get_memories(
    client: AsyncClient, session: AsyncSession, status: ElderStatus
) -> None:
    elder = await add_elder(session, status=status)
    await add_fact(session, elder, "Bà có con gái tên Mai.")
    await add_memory(session, elder, "Bà hay đi khám ở đây.", "Bệnh viện Bạch Mai")

    context = context_of(await pre_call(client))

    assert "memory_summary" not in context and "frequent_places" not in context
