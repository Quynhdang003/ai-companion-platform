import unicodedata

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMError
from app.models import ScamPattern, ScamType
from app.services.rag.ingest import SyncResult, embedding_text
from app.services.scam.patterns import (
    MAX_PATTERN_CHARS,
    InvalidPatternError,
    PatternIn,
    sync_patterns,
)
from app.services.scam.search import pair_ids, search_patterns, word_pairs
from tests.fakes import FakeLLMClient, QueryVectorLLM, SlowLLM

POLICE = PatternIn(
    ScamType.POLICE_IMPERSONATION,
    "Công an báo liên quan vụ án rửa tiền",
    "Kẻ gian xưng là công an, nói nạn nhân liên quan vụ án rửa tiền, yêu cầu chuyển tiền "
    "vào tài khoản tạm giữ và giữ bí mật với con cháu.",
)
BANK = PatternIn(
    ScamType.BANK_IMPERSONATION,
    "Ngân hàng báo khóa tài khoản, xin mã OTP",
    "Kẻ gian xưng là nhân viên ngân hàng, báo tài khoản bị khóa, xin mã OTP và mật khẩu "
    "để mở khóa.",
)
CHARITY = PatternIn(
    ScamType.FAKE_CHARITY,
    "Quyên góp cho người bệnh nặng",
    "Kẻ gian kể hoàn cảnh người bệnh nặng cần tiền mổ gấp, xin quyên góp vào tài khoản cá nhân.",
)


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
async def patterns(session: AsyncSession, llm: FakeLLMClient) -> None:
    await sync_patterns(session, llm, [POLICE, BANK, CHARITY])


async def stored(session: AsyncSession, title: str) -> ScamPattern:
    return await session.scalar(select(ScamPattern).where(ScamPattern.title == title))


# --- storage ---------------------------------------------------------------------------


async def test_new_patterns_are_embedded_in_one_request(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    results = await sync_patterns(session, llm, [POLICE, BANK])

    assert results == [SyncResult.CREATED, SyncResult.CREATED]
    [(texts, task)] = llm.embedded
    assert task == "document"
    assert texts == [embedding_text(p.title, p.content) for p in (POLICE, BANK)]
    police = await stored(session, POLICE.title)
    assert (police.scam_type, police.content) == (ScamType.POLICE_IMPERSONATION, POLICE.content)


async def test_unchanged_patterns_are_not_embedded_again(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    results = await sync_patterns(session, llm, [POLICE, BANK, CHARITY])

    assert results == [SyncResult.UNCHANGED] * 3
    assert len(llm.embedded) == 1


async def test_only_changed_content_is_re_embedded(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    police_id = (await stored(session, POLICE.title)).id
    new_police = PatternIn(POLICE.scam_type, POLICE.title, "Xưng là công an, đòi chuyển tiền.")
    retyped_bank = PatternIn(ScamType.OTHER, BANK.title, BANK.content, source="data/x.md")

    results = await sync_patterns(session, llm, [new_police, retyped_bank, CHARITY])

    assert results == [SyncResult.UPDATED, SyncResult.UPDATED, SyncResult.UNCHANGED]
    assert llm.embedded[-1] == ([embedding_text(POLICE.title, new_police.content)], "document")
    police = await stored(session, POLICE.title)
    assert (police.id, police.content) == (police_id, new_police.content)
    bank = await stored(session, BANK.title)
    assert (bank.scam_type, bank.source) == (ScamType.OTHER, "data/x.md")


async def test_failed_embedding_keeps_the_stored_version(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    llm.embed_error = LLMError("down")

    with pytest.raises(LLMError):
        await sync_patterns(session, llm, [PatternIn(POLICE.scam_type, POLICE.title, "Mới.")])

    assert (await stored(session, POLICE.title)).content == POLICE.content


@pytest.mark.parametrize(
    "bad",
    [
        [PatternIn(ScamType.OTHER, "Trống", "  ")],
        [PatternIn(ScamType.OTHER, " ", "Nội dung.")],
        [PatternIn(ScamType.OTHER, "Dài", "a" * (MAX_PATTERN_CHARS + 1))],
        [POLICE, PatternIn(ScamType.OTHER, POLICE.title, "Trùng tiêu đề.")],
    ],
    ids=["empty content", "empty title", "too long", "duplicate title"],
)
async def test_invalid_patterns_are_rejected_before_embedding(
    session: AsyncSession, llm: FakeLLMClient, bad: list[PatternIn]
) -> None:
    with pytest.raises(InvalidPatternError):
        await sync_patterns(session, llm, bad)

    assert llm.embedded == []


async def test_search_text_covers_title_and_content_without_diacritics(
    session: AsyncSession, patterns: None
) -> None:
    def matching(phrase: str) -> str:
        return (
            f"SELECT title FROM scam_patterns WHERE search_text @@ to_tsquery('simple', '{phrase}')"
        )

    assert (await session.scalars(text(matching("tam <-> giu")))).all() == [POLICE.title]
    # Only in CHARITY's title.
    assert (await session.scalars(text(matching("benh <-> nang")))).all() == [CHARITY.title]


# --- word pairs ------------------------------------------------------------------------


def test_word_pairs_stay_within_a_clause_and_skip_function_words() -> None:
    assert word_pairs("Chuyển tiền vào tài khoản lạ, gấp!") == [
        "chuyen tien",
        "tai khoan",
        "khoan la",
    ]


def test_word_pairs_are_distinct_and_capped() -> None:
    assert word_pairs("tài khoản tài khoản. TÀI KHOẢN") == ["tai khoan", "khoan tai"]
    assert word_pairs("mot hai ba bon nam sau bay", limit=2) == ["hai ba", "ba bon"]


def test_word_pairs_handle_decomposed_diacritics() -> None:
    assert word_pairs(unicodedata.normalize("NFD", "Đọc mã OTP")) == ["doc ma", "ma otp"]


def test_no_pairs_from_single_words_or_punctuation() -> None:
    assert word_pairs("Alô?! Dạ.") == []


# --- hybrid search ---------------------------------------------------------------------


async def test_situation_without_diacritics_finds_its_pattern(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    hits = await search_patterns(
        session,
        llm,
        "co nguoi xung la cong an bao lien quan vu an rua tien, "
        "bat chuyen tien vao tai khoan tam giu",
    )

    assert [hit.title for hit in hits] == [POLICE.title]
    assert hits[0].scam_type is ScamType.POLICE_IMPERSONATION


async def test_patterns_with_more_shared_pairs_rank_first(
    session: AsyncSession, patterns: None
) -> None:
    ids = await pair_ids(
        session, "Người gọi xưng là nhân viên ngân hàng, báo tài khoản bị khóa, xin mã OTP.", 5
    )

    assert ids[0] == (await stored(session, BANK.title)).id


async def test_sharing_a_couple_of_common_pairs_is_not_a_match(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    # Shares only "chuyen tien" and "tai khoan" with POLICE: below MIN_PAIR_MATCHES.
    situation = "Cháu tôi chuyển tiền vào tài khoản tiết kiệm cho bà."

    assert await search_patterns(session, llm, situation) == []


async def test_close_embedding_alone_finds_the_pattern(
    session: AsyncSession, patterns: None
) -> None:
    llm = QueryVectorLLM(query_as=embedding_text(CHARITY.title, CHARITY.content))

    hits = await search_patterns(session, llm, "xyzw")

    assert [hit.title for hit in hits] == [CHARITY.title]


async def test_unrelated_situation_finds_nothing(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    assert await search_patterns(session, llm, "Hôm nay trời đẹp, bác đi tập thể dục.") == []
    assert await search_patterns(session, llm, "  ?! ") == []


@pytest.mark.parametrize("failure", ["error", "timeout"])
async def test_search_falls_back_to_word_pairs_when_embedding_fails(
    session: AsyncSession, patterns: None, failure: str
) -> None:
    llm = SlowLLM() if failure == "timeout" else FakeLLMClient()
    if failure == "error":
        llm.embed_error = LLMError("down")

    hits = await search_patterns(
        session, llm, "Ngân hàng báo tài khoản bị khóa, xin mã OTP.", embed_timeout=0.05
    )

    assert hits and hits[0].title == BANK.title


async def test_limit_is_respected(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    situation = (
        "Xưng là công an, nói liên quan vụ án rửa tiền. Rồi nhân viên ngân hàng báo tài khoản "
        "bị khóa, xin mã OTP. Rồi xin quyên góp cho người bệnh nặng cần tiền mổ gấp."
    )

    assert len(await search_patterns(session, llm, situation)) == 3
    assert len(await search_patterns(session, llm, situation, limit=1)) == 1
