import asyncio
from collections.abc import Sequence

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import EmbedTask, LLMError
from app.models import KbChunk, KbDocument
from app.services.rag.ingest import (
    EmptyDocumentError,
    SyncResult,
    add_document,
    embedding_text,
    sync_document,
)
from app.services.rag.search import fold, query_words, rrf_merge, search_kb, trigram_ids
from tests.fakes import FakeLLMClient, fake_vector

EMERGENCY = "Số điện thoại khẩn cấp"
EMERGENCY_TEXT = (
    "Gọi 113 khi cần công an giúp đỡ. Gọi 114 khi có cháy nổ, cần cứu hỏa. "
    "Gọi 115 khi cần xe cấp cứu đưa người bệnh đi viện."
)
HOSPITAL = "Bệnh viện ở Hà Nội"
HOSPITAL_TEXT = "Bệnh viện Bạch Mai ở số 78 đường Giải Phóng, quận Đống Đa, Hà Nội."


class QueryVectorLLM(FakeLLMClient):
    """Embeds every query as `query_as`, to exercise the vector ranking alone."""

    def __init__(self, query_as: str) -> None:
        super().__init__()
        self.query_as = query_as

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        if task == "query":
            return [fake_vector(self.query_as) for _ in texts]
        return await super().embed(texts, task=task)


class SlowLLM(FakeLLMClient):
    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        if task == "query":
            await asyncio.sleep(1)
        return await super().embed(texts, task=task)


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
async def kb(session: AsyncSession, llm: FakeLLMClient) -> None:
    await add_document(session, llm, title=EMERGENCY, content=EMERGENCY_TEXT)
    await add_document(session, llm, title=HOSPITAL, content=HOSPITAL_TEXT, source="seed")


async def chunk_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(KbChunk))


# --- ingestion -------------------------------------------------------------------------


async def test_document_is_chunked_and_embedded_with_its_title(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    content = " ".join(f"Câu thứ {i} nói về an toàn khi nghe điện thoại lạ." for i in range(60))

    document = await add_document(session, llm, title="An toàn", content=content)

    chunks = (
        await session.scalars(
            select(KbChunk).where(KbChunk.document_id == document.id).order_by(KbChunk.chunk_index)
        )
    ).all()
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    [(texts, task)] = llm.embedded
    assert task == "document"
    assert texts == [embedding_text("An toàn", c.content) for c in chunks]
    assert list(chunks[0].embedding) == pytest.approx(fake_vector(texts[0]), abs=1e-6)


async def test_search_text_is_generated_without_diacritics(session: AsyncSession, kb: None) -> None:
    matches = await session.scalar(
        text("SELECT count(*) FROM kb_chunks WHERE search_text @@ to_tsquery('simple', 'dong')")
    )
    assert matches == 1  # "Đống Đa"


async def test_empty_document_is_rejected(session: AsyncSession, llm: FakeLLMClient) -> None:
    with pytest.raises(EmptyDocumentError):
        await add_document(session, llm, title="Trống", content=" \n ")


async def test_sync_creates_skips_unchanged_and_replaces_in_place(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    assert await sync_document(session, llm, title="T", content="Một.") is SyncResult.CREATED
    doc_id = await session.scalar(select(KbDocument.id))
    assert await sync_document(session, llm, title="T", content="Một.") is SyncResult.UNCHANGED
    assert len(llm.embedded) == 1

    assert await sync_document(session, llm, title="T", content="Hai. Ba.") is SyncResult.UPDATED

    document = await session.scalar(select(KbDocument))
    assert (document.id, document.content) == (doc_id, "Hai. Ba.")
    contents = (await session.scalars(select(KbChunk.content))).all()
    assert contents == ["Hai. Ba."]


async def test_failed_embedding_keeps_the_stored_version(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    await sync_document(session, llm, title="T", content="Một.")
    llm.embed_error = LLMError("down")

    with pytest.raises(LLMError):
        await sync_document(session, llm, title="T", content="Hai.")

    assert (await session.scalars(select(KbChunk.content))).all() == ["Một."]


# --- ranking helpers -------------------------------------------------------------------


def test_rrf_prefers_items_ranked_by_several_lists() -> None:
    merged = rrf_merge([["a", "b", "c"], ["b", "d"], ["b", "a"]], k=60)

    assert [item for item, _ in merged] == ["b", "a", "d", "c"]
    assert merged[0][1] == pytest.approx(1 / 62 + 1 / 61 + 1 / 61)


def test_query_words_are_distinct_accent_free_words() -> None:
    assert query_words("Bệnh viện ở đâu? Bệnh! Đường ĐI") == [
        "benh",
        "vien",
        "o",
        "dau",
        "duong",
        "di",
    ]
    # "báo" and "bao" are the same word once accents are gone.
    assert query_words("báo bao bão") == ["bao"]
    assert query_words("a & b | !c:* (d)") == ["a", "b", "c", "d"]
    assert query_words(" ?! _ ") == []


def test_fold_matches_unaccent() -> None:
    assert fold("Đống Đa, cứu hỏa, người ưng ý") == "Dong Da, cuu hoa, nguoi ung y"


# --- hybrid search ---------------------------------------------------------------------


async def test_query_without_diacritics_finds_the_chunk(
    session: AsyncSession, llm: FakeLLMClient, kb: None
) -> None:
    hits = await search_kb(session, llm, "benh vien bach mai o dau")

    assert hits[0].title == HOSPITAL
    assert "Giải Phóng" in hits[0].content


async def test_d_with_stroke_matches_plain_d(
    session: AsyncSession, llm: FakeLLMClient, kb: None
) -> None:
    # "đưa", "đi" -> "dua", "di"
    hits = await search_kb(session, llm, "goi dua nguoi benh di vien")

    assert hits[0].title == EMERGENCY


async def test_sharing_a_few_common_words_is_not_a_match(
    session: AsyncSession, llm: FakeLLMClient, kb: None
) -> None:
    # Only "gọi" and "có" appear in the KB: below MIN_WORD_COVERAGE.
    assert await search_kb(session, llm, "gọi hỏi giá vàng hôm nay có tăng") == []


async def test_typo_is_found_by_trigram(session: AsyncSession, kb: None) -> None:
    [chunk_id] = await trigram_ids(session, "Bach Maii", 5)

    content = await session.scalar(select(KbChunk.content).where(KbChunk.id == chunk_id))
    assert "Bạch Mai" in content


async def test_close_embedding_alone_finds_the_chunk(session: AsyncSession, kb: None) -> None:
    llm = QueryVectorLLM(query_as=embedding_text(HOSPITAL, HOSPITAL_TEXT))

    hits = await search_kb(session, llm, "xyzw")

    assert [hit.title for hit in hits] == [HOSPITAL]


async def test_unrelated_query_finds_nothing(
    session: AsyncSession, llm: FakeLLMClient, kb: None
) -> None:
    assert await search_kb(session, llm, "xyzw qqq") == []
    assert await search_kb(session, llm, "  ?! ") == []


@pytest.mark.parametrize("failure", ["error", "timeout"])
async def test_search_falls_back_to_lexical_when_embedding_fails(
    session: AsyncSession, kb: None, failure: str
) -> None:
    llm = SlowLLM() if failure == "timeout" else FakeLLMClient()
    if failure == "error":
        llm.embed_error = LLMError("down")

    hits = await search_kb(session, llm, "goi xe cap cuu", embed_timeout=0.05)

    assert hits and hits[0].title == EMERGENCY


async def test_limit_is_respected(session: AsyncSession, llm: FakeLLMClient, kb: None) -> None:
    assert len(await search_kb(session, llm, "goi benh vien cap cuu ha noi", limit=1)) == 1
