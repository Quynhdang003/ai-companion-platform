import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMError, LLMNotConfiguredError, LLMRateLimitedError, SchemaT
from app.models import AssessedBy, RiskLevel, ScamType, Signal
from app.services.scam.engine import FallbackReason, assess
from app.services.scam.patterns import PatternIn, sync_patterns
from tests.fakes import FakeLLMClient

BANK = PatternIn(
    ScamType.BANK_IMPERSONATION,
    "Ngân hàng báo khóa tài khoản, xin mã OTP",
    "Kẻ gian xưng là nhân viên ngân hàng, báo tài khoản bị khóa, xin mã OTP và mật khẩu "
    "để mở khóa.",
)
RELATIVE = PatternIn(
    ScamType.RELATIVE_IMPERSONATION,
    "Cháu đổi số, xin tiền gấp",
    "Kẻ gian xưng là cháu, nói vừa đổi số điện thoại, đang gặp chuyện cần tiền gấp, nhờ "
    "chuyển khoản vào tài khoản của bạn.",
)

# Not decisive for layer 1: a relative's story and a money request (medium).
RELATIVE_ASKS = "Có người xưng là cháu, nói vừa đổi số điện thoại, xin bác chuyển tiền."
DECISIVE = "Người xưng nhân viên ngân hàng xin bác đọc mã OTP vừa gửi về."
HARMLESS = "Hôm nay trời đẹp, bác đi tập thể dục."

HIGH_RELATIVE = {
    "risk_level": "high",
    "scam_type": "relative_impersonation",
    "signals": ["relative", "money_transfer", "urgency"],
    "reason": "Người lạ xưng cháu đổi số và xin tiền.",
}


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
async def patterns(session: AsyncSession) -> None:
    await sync_patterns(session, FakeLLMClient(), [BANK, RELATIVE])


async def test_a_decisive_rule_answers_without_search_or_llm(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    result = await assess(session, llm, DECISIVE, timeout=4)

    assert (result.level, result.scam_type) == (RiskLevel.HIGH, ScamType.BANK_IMPERSONATION)
    assert (result.assessed_by, result.decisive_rule) == (AssessedBy.RULES, "credentials")
    assert llm.prompts == [] and llm.embedded == []


async def test_the_classifier_decides_otherwise(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    llm.replies.append(HIGH_RELATIVE)

    result = await assess(session, llm, RELATIVE_ASKS, timeout=4)

    assert (result.level, result.scam_type) == (
        RiskLevel.HIGH,
        ScamType.RELATIVE_IMPERSONATION,
    )
    assert result.assessed_by is AssessedBy.LLM
    assert result.reason == HIGH_RELATIVE["reason"]
    # Layer-1 signals and the classifier's, together.
    assert {Signal.RELATIVE, Signal.MONEY_TRANSFER, Signal.URGENCY} <= result.signals


async def test_the_prompt_holds_situation_patterns_and_hints(
    session: AsyncSession, llm: FakeLLMClient, patterns: None
) -> None:
    llm.replies.append(HIGH_RELATIVE)

    result = await assess(session, llm, RELATIVE_ASKS, timeout=4)

    [prompt] = llm.prompts
    assert RELATIVE_ASKS in prompt
    assert f"[relative_impersonation] {RELATIVE.title}" in prompt
    assert "money_transfer" in prompt.split("Keyword signals:")[1].splitlines()[0]
    assert result.pattern_titles[0] == RELATIVE.title


async def test_the_classifier_can_clear_a_look_alike(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    llm.replies.append({"risk_level": "low", "scam_type": "other", "reason": "Cháu quen."})

    result = await assess(
        session, llm, "Cháu gái gọi về nhờ bác chuyển tiền đóng học phí.", timeout=4
    )

    assert (result.level, result.scam_type, result.assessed_by) == (
        RiskLevel.LOW,
        None,
        AssessedBy.LLM,
    )


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (LLMRateLimitedError("429"), FallbackReason.RATE_LIMITED),
        (LLMNotConfiguredError("no key"), FallbackReason.NOT_CONFIGURED),
        (LLMError("500"), FallbackReason.ERROR),
        # High without a type: rejected by the schema.
        ({"risk_level": "high", "scam_type": None}, FallbackReason.ERROR),
    ],
    ids=["rate limited", "no key", "api error", "invalid output"],
)
async def test_layer_1_answers_when_the_classifier_fails(
    session: AsyncSession,
    llm: FakeLLMClient,
    error: Exception | dict[str, object],
    reason: FallbackReason,
) -> None:
    llm.replies.append(error)

    result = await assess(session, llm, RELATIVE_ASKS, timeout=4)

    assert (result.level, result.scam_type) == (
        RiskLevel.MEDIUM,
        ScamType.RELATIVE_IMPERSONATION,
    )
    assert (result.assessed_by, result.fallback_reason) == (AssessedBy.RULES_FALLBACK, reason)


class SlowClassifier(FakeLLMClient):
    async def generate_json(
        self, prompt: str, schema: type[SchemaT], *, system: str | None = None
    ) -> SchemaT:
        await asyncio.sleep(2)
        return await super().generate_json(prompt, schema, system=system)


async def test_layer_1_answers_when_the_classifier_is_late(session: AsyncSession) -> None:
    llm = SlowClassifier()
    llm.replies.append(HIGH_RELATIVE)

    result = await assess(session, llm, RELATIVE_ASKS, timeout=1)

    assert result.level is RiskLevel.MEDIUM
    assert result.fallback_reason is FallbackReason.TIMEOUT


async def test_no_classifier_call_when_the_budget_is_spent(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    result = await assess(session, llm, RELATIVE_ASKS, timeout=0.1)

    assert result.fallback_reason is FallbackReason.TIMEOUT
    assert llm.prompts == []


async def test_below_medium_has_no_type_on_fallback(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    llm.replies.append(LLMError("500"))

    # One signal only (money transfer): low, and layer 1 would name "other".
    result = await assess(session, llm, "Cháu nhờ bác chuyển tiền đóng học phí.", timeout=4)

    assert (result.level, result.scam_type) == (RiskLevel.LOW, None)


async def test_harmless_talk_still_goes_to_the_classifier(
    session: AsyncSession, llm: FakeLLMClient
) -> None:
    llm.replies.append({"risk_level": "none"})

    result = await assess(session, llm, HARMLESS, timeout=4)

    assert (result.level, result.assessed_by) == (RiskLevel.NONE, AssessedBy.LLM)
    assert result.signals == frozenset()
