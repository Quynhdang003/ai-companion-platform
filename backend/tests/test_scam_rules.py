import pytest

from app.models import RiskLevel, ScamType
from app.services.scam.rules import PHRASES, Signal, assess_rules, find_signals
from scripts.scam_cases import load_cases

CASES = load_cases()

# --- signals ---------------------------------------------------------------------------


def test_every_signal_has_phrases() -> None:
    assert set(PHRASES) == set(Signal)
    assert all(PHRASES[signal] for signal in Signal)


@pytest.mark.parametrize(
    "situation",
    ["Họ xin mã OTP của bác.", "ho xin ma otp cua bac", "Họ bảo đọc mã ô tê pê."],
)
def test_phrases_match_with_or_without_diacritics(situation: str) -> None:
    assert Signal.CREDENTIALS in find_signals(situation)


@pytest.mark.parametrize(
    ("situation", "absent"),
    [
        # Folded alike, but not the scam phrase.
        ("Hôm qua bác bị mất ví ở chợ.", Signal.SECRECY),  # "bị mất", not "giữ bí mật"
        ("Cháu nó muốn gặp bác.", Signal.URGENCY),  # "gặp", not "gấp"
        ("Bác trồng mấy chậu hoa hồng.", Signal.EASY_PROFIT),
        ("Huyết áp của bác lại cao.", Signal.EASY_PROFIT),
        ("Bác bỏ thuốc lá được một năm rồi.", Signal.MIRACLE_CURE),
    ],
)
def test_look_alike_words_are_not_signals(situation: str, absent: Signal) -> None:
    assert absent not in find_signals(situation)


def test_phrases_match_whole_words_only() -> None:
    # "cong anh" contains "cong an" as text, not as words.
    assert find_signals("Ông Công Anh gọi hỏi thăm.") == frozenset()


# --- levels ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("situation", "rule"),
    [
        ("Họ hỏi mật khẩu thẻ của bác.", "credentials"),
        ("Họ bảo chuyển vào tài khoản an toàn.", "safe_account"),
        ("Người xưng công an bảo bác đọc số căn cước.", "authority_asks"),
        ("Họ dặn giữ bí mật rồi bảo chuyển khoản.", "secret_payment"),
        ("Nhân viên ngân hàng gửi đường link bảo bấm vào.", "impostor_link"),
        ("Họ bảo góp vốn, không có rủi ro.", "easy_profit_payment"),
        ("Thuốc chữa khỏi hẳn bệnh, phải chuyển khoản trước.", "miracle_cure_payment"),
        ("Bác trúng thưởng, chỉ cần đóng phí nhận quà.", "prize_payment"),
    ],
)
def test_decisive_rules_make_the_level_high(situation: str, rule: str) -> None:
    result = assess_rules(situation)

    assert (result.level, result.decisive_rule) == (RiskLevel.HIGH, rule)
    assert result.decisive


@pytest.mark.parametrize(
    "situation",
    [
        "Có người xưng là cháu, xin tiền.",  # ask + story
        "Công an gọi báo bác liên quan vụ án.",  # story + pressure
        "Có người gọi bảo chuyển tiền ngay lập tức.",  # ask + pressure
        "Có người bảo có thuốc chữa khỏi hẳn tiểu đường.",  # claim too good to be true
    ],
)
def test_suspicious_but_not_decisive_is_medium(situation: str) -> None:
    result = assess_rules(situation)

    assert result.level is RiskLevel.MEDIUM
    assert not result.decisive


def test_a_single_signal_is_low() -> None:
    result = assess_rules("Cháu nhờ bác chuyển tiền đóng học phí.")

    assert (result.level, result.signals) == (RiskLevel.LOW, {Signal.MONEY_TRANSFER})
    assert result.scam_type is ScamType.OTHER


def test_no_signal_is_none_without_a_type() -> None:
    result = assess_rules("Hôm nay trời đẹp, bác đi tập thể dục.")

    assert (result.level, result.scam_type, result.signals) == (RiskLevel.NONE, None, set())


# --- scam type -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("situation", "scam_type"),
    [
        # Who they claim to be outweighs a detail of the story.
        ("Công ty du lịch cam kết cho thuê lại, trả lợi nhuận.", ScamType.RESORT_CONTRACT),
        ("Có người xưng là cháu, bảo đang bị công an giữ.", ScamType.RELATIVE_IMPERSONATION),
        # Equal weight: the type declared first wins.
        ("Họ mời mua thực phẩm chức năng và đi du lịch.", ScamType.HEALTH_PRODUCT),
        # No story: an OTP request is a fake bank, anything else is "other".
        ("Có người hỏi mã OTP.", ScamType.BANK_IMPERSONATION),
        ("Có người bảo chuyển tiền ngay lập tức.", ScamType.OTHER),
    ],
)
def test_scam_type_comes_from_the_strongest_cues(situation: str, scam_type: ScamType) -> None:
    assert assess_rules(situation).scam_type is scam_type


# --- the labelled test set -------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_decisive_only_on_high_cases_and_with_their_type(case) -> None:
    result = assess_rules(case.situation)

    if result.decisive:
        assert case.level is RiskLevel.HIGH, result.decisive_rule
        assert result.scam_type is case.scam_type


@pytest.mark.parametrize(
    "case", [c for c in CASES if c.level is RiskLevel.HIGH], ids=lambda c: c.id
)
def test_every_high_case_gets_a_warning_from_rules_alone(case) -> None:
    assert assess_rules(case.situation).level.rank >= RiskLevel.MEDIUM.rank


@pytest.mark.parametrize(
    "case", [c for c in CASES if c.level is RiskLevel.NONE], ids=lambda c: c.id
)
def test_harmless_cases_stay_at_most_low(case) -> None:
    assert assess_rules(case.situation).level.rank <= RiskLevel.LOW.rank
