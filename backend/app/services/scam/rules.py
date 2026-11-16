"""Layer 1 of the Scam Risk Engine: phrase rules over the situation, no DB and no LLM.

Fast and explainable. It finds signals (what the caller is asked to do, pressure, who the
other side claims to be or what they offer), then:
- a decisive rule (asking for an OTP, a "tài khoản tạm giữ", "công an" + a payment, ...)
  makes the level high. These are cases no legitimate caller produces, so the engine
  answers at once without the classifier;
- otherwise the level is only a fallback for when the classifier fails, and the signals
  are hints for it.

Phrases are matched accent-free on whole words, so STT text without diacritics matches
too. Folding merges some words ("bí mật" / "bị mất", "gấp" / "gặp", "lãi" / "lại"), so
every phrase is chosen to stay unambiguous once folded: "giữ bí mật", not "bí mật".
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from app.models import RiskLevel, ScamType, Signal
from app.services.rag.search import words

PHRASES: dict[Signal, tuple[str, ...]] = {
    Signal.MONEY_TRANSFER: (
        "chuyển tiền",
        "chuyển khoản",
        "chuyển trả",
        "chuyển ngay",
        "chuyển gấp",
        "vào tài khoản",
        "nạp tiền",
        "nạp thêm",
        "nạp vào",
        "nộp tiền",
        "nộp phạt",
        "đóng phí",
        "trả phí",
        "trả trước",
        "đặt cọc",
        "tiền cọc",
        "gửi tiền",
        "rút tiền",
        "rút sổ tiết kiệm",
        "mua vàng",
        "quẹt thẻ",
        "trả góp",
        "góp vốn",
        "góp tiền",
        "xin tiền",
        "vay tiền",
        "cần tiền",
        "thu tiền",
    ),
    Signal.CREDENTIALS: (
        "otp",
        "ô tê pê",
        "mã xác nhận",
        "mã xác thực",
        "mã vừa gửi",
        "mã gửi về",
        "mã số vừa",
        "mã số gửi",
        "đọc mã",
        "mật khẩu",
        "mã pin",
        "cvv",
        "ba số mặt sau thẻ",
        "ba số ở mặt sau",
        "số bảo mật",
    ),
    Signal.PERSONAL_INFO: (
        "số căn cước",
        "căn cước công dân",
        "cccd",
        "chứng minh nhân dân",
        "số tài khoản",
        "số dư",
        "số thẻ",
        "ảnh khuôn mặt",
        "quay video khuôn mặt",
        "sinh trắc",
        "bao nhiêu tiền trong",
    ),
    Signal.LINK_OR_APP: (
        "link",
        "đường dẫn",
        "cài ứng dụng",
        "cài app",
        "cài đặt ứng dụng",
        "tải ứng dụng",
        "tải app",
        "cài phần mềm",
    ),
    Signal.SAFE_ACCOUNT: (
        "tài khoản tạm giữ",
        "tài khoản an toàn",
        "chứng minh trong sạch",
        "kiểm tra nguồn gốc tiền",
        "kiểm tra nguồn gốc tài sản",
    ),
    Signal.PERSONAL_ACCOUNT: (
        "tài khoản cá nhân",
        "tài khoản lạ",
        "tài khoản của họ",
        "tài khoản người khác",
        "tài khoản của bạn",
        "tài khoản khác",
        "tài khoản không mang tên",
    ),
    Signal.URGENCY: (
        "ngay lập tức",
        "ngay bây giờ",
        "ngay hôm nay",
        "trong hôm nay",
        "chỉ hôm nay",
        "chiều nay",
        "vài phút",
        "khẩn cấp",
        "tiền gấp",
        "chuyển gấp",
        "khoản gấp",
        "gấp lắm",
        "rất gấp",
        "chuyển ngay",
        "chỉ còn vài suất",
    ),
    Signal.SECRECY: (
        "giữ bí mật",
        "đừng nói với",
        "đừng nói cho",
        "không được nói",
        "không được kể",
        "đừng kể",
        "không nói với ai",
        "đừng cho ai biết",
        "không cho ai biết",
    ),
    Signal.THREAT: (
        "lệnh bắt",
        "bắt giam",
        "bị bắt",
        "sẽ bắt",
        "khởi tố",
        "truy nã",
        "triệu tập",
        "rửa tiền",
        "ma túy",
        "vụ án",
        "đường dây",
        "phạt nguội",
        "tước bằng",
        "tước giấy phép",
        "bị khóa",
        "khóa tài khoản",
        "cắt điện",
        "nợ thuế",
        "nợ tiền điện",
        "hàng cấm",
        "gặp hạn",
    ),
    Signal.AUTHORITY: (
        "công an",
        "cảnh sát",
        "viện kiểm sát",
        "tòa án",
        "điều tra viên",
        "cơ quan điều tra",
        "cán bộ điều tra",
        "csgt",
    ),
    Signal.BANK: (
        "nhân viên ngân hàng",
        "tổng đài ngân hàng",
        "ngân hàng gọi",
        "ngân hàng báo",
        "ngân hàng nhắn",
        "tên ngân hàng",
        "tin nhắn ngân hàng",
        "chăm sóc khách hàng",
        "thẻ tín dụng",
        "hạn mức",
    ),
    Signal.RELATIVE: (
        "xưng là cháu",
        "xưng là con",
        "xưng cháu",
        "cháu đây",
        "con đây",
        "đổi số",
        "số mới",
        "bạn của con",
        "bạn của cháu",
        "giáo viên của cháu",
        "thầy giáo của cháu",
        "cô giáo của cháu",
        "zalo của con",
        "zalo của cháu",
        "facebook của con",
        "facebook của cháu",
        "tài khoản zalo",
        "tài khoản facebook",
        "hình mờ",
        "giọng giống",
    ),
    Signal.RELATIVE_EMERGENCY: (
        "tai nạn",
        "cấp cứu",
        "cần mổ",
        "tiền mổ",
        "đang mổ",
        "viện phí",
        "nhập viện",
        "bị ngất",
        "ngất xỉu",
        "bị công an giữ",
        "ở đồn",
        "đền tiền",
        "mất ví",
    ),
    Signal.INVESTMENT: (
        "đầu tư",
        "góp vốn",
        "tiền ảo",
        "tiền điện tử",
        "chứng khoán",
        "cổ phiếu",
        "ngoại hối",
        "sàn giao dịch",
        "đất nền",
        "dự án",
        "nhóm zalo",
        "nhóm telegram",
        "chuyên gia",
    ),
    Signal.EASY_PROFIT: (
        "không rủi ro",
        "không có rủi ro",
        "chắc chắn lãi",
        "lãi mỗi ngày",
        "mỗi ngày lãi",
        "phần trăm mỗi ngày",
        "lãi khủng",
        "lãi gấp đôi",
        "gấp đôi",
        "nhân đôi",
        "cam kết lợi nhuận",
        "cam kết cho thuê",
        "bảo đảm hoàn vốn",
        "hoàn vốn",
        "việc nhẹ lương cao",
        "nhận hoa hồng",
        "hưởng hoa hồng",
        "tiền hoa hồng",
        "khoe lãi",
    ),
    Signal.HEALTH_PRODUCT: (
        "thực phẩm chức năng",
        "thuốc bổ",
        "hội thảo sức khỏe",
        "khám bệnh miễn phí",
        "khám miễn phí",
        "máy massage",
        "đệm từ",
        "máy lọc nước",
        "liệu trình",
        "dược sĩ",
        "tặng thuốc",
        "bán thuốc",
        "mua thuốc",
        "giới thiệu thuốc",
        "thuốc nhập khẩu",
    ),
    Signal.MIRACLE_CURE: (
        "chữa khỏi hoàn toàn",
        "khỏi hoàn toàn",
        "chữa khỏi hẳn",
        "khỏi hẳn",
        "dứt điểm",
        "đặc trị",
        "gia truyền",
        "thần dược",
        "bỏ thuốc đang",
        "bỏ thuốc bác sĩ",
        "bỏ thuốc của bác sĩ",
        "ngừng thuốc",
    ),
    Signal.PRIZE: (
        "trúng thưởng",
        "trúng giải",
        "được tặng",
        "tặng quà",
        "quà tặng",
        "nhận quà",
        "tri ân",
        "được chọn",
    ),
    Signal.RESORT: (
        "kỳ nghỉ",
        "nghỉ dưỡng",
        "du lịch",
        "tour",
        "thẻ hội viên",
        "hợp đồng",
        "khách sạn",
        "hành hương",
    ),
    Signal.DONATION: (
        "quyên góp",
        "ủng hộ",
        "công đức",
        "từ thiện",
        "làm lễ",
        "giải hạn",
        "cầu an",
        "chữ thập đỏ",
        "thiện nguyện",
        "nhà sư",
    ),
    Signal.SERVICE: (
        "điện lực",
        "tiền điện",
        "bảo hiểm xã hội",
        "bhxh",
        "cơ quan thuế",
        "cục thuế",
        "hoàn thuế",
        "nợ thuế",
        "lương hưu",
        "bưu điện",
        "bưu phẩm",
        "bưu kiện",
        "giao hàng",
        "shipper",
        "đơn hàng",
        "chuyển nhầm",
    ),
}

ASKS = frozenset(
    {
        Signal.MONEY_TRANSFER,
        Signal.CREDENTIALS,
        Signal.PERSONAL_INFO,
        Signal.LINK_OR_APP,
        Signal.PERSONAL_ACCOUNT,
    }
)
PRESSURE = frozenset({Signal.URGENCY, Signal.SECRECY, Signal.THREAT})
# Claims too good to be true: suspicious on their own.
STRONG_CLAIMS = frozenset({Signal.EASY_PROFIT, Signal.MIRACLE_CURE})

# Signals that point to a scam type, with their weight. Who they claim to be or what they
# sell weighs 2; a detail of the story weighs 1, so "cam kết cho thuê lại" in a resort
# offer stays a resort scam.
TYPE_CUES: dict[Signal, tuple[ScamType, int]] = {
    Signal.AUTHORITY: (ScamType.POLICE_IMPERSONATION, 2),
    Signal.SAFE_ACCOUNT: (ScamType.POLICE_IMPERSONATION, 1),
    Signal.BANK: (ScamType.BANK_IMPERSONATION, 2),
    Signal.RELATIVE: (ScamType.RELATIVE_IMPERSONATION, 2),
    Signal.RELATIVE_EMERGENCY: (ScamType.RELATIVE_IMPERSONATION, 1),
    Signal.INVESTMENT: (ScamType.INVESTMENT, 2),
    Signal.EASY_PROFIT: (ScamType.INVESTMENT, 1),
    Signal.HEALTH_PRODUCT: (ScamType.HEALTH_PRODUCT, 2),
    Signal.MIRACLE_CURE: (ScamType.HEALTH_PRODUCT, 1),
    Signal.RESORT: (ScamType.RESORT_CONTRACT, 2),
    Signal.PRIZE: (ScamType.RESORT_CONTRACT, 1),
    Signal.DONATION: (ScamType.FAKE_CHARITY, 2),
    Signal.SERVICE: (ScamType.OTHER, 2),
}
STORY = frozenset(TYPE_CUES)


@dataclass(frozen=True)
class Rule:
    """Fires when the situation has every `all_of` signal and, if given, one of `any_of`."""

    name: str
    all_of: frozenset[Signal]
    any_of: frozenset[Signal] = frozenset()

    def fires(self, signals: frozenset[Signal]) -> bool:
        return self.all_of <= signals and (not self.any_of or bool(self.any_of & signals))


def _rule(name: str, all_of: Iterable[Signal], any_of: Iterable[Signal] = ()) -> Rule:
    return Rule(name, frozenset(all_of), frozenset(any_of))


DECISIVE_RULES = (
    # Banks, police and relatives never ask for these by phone.
    _rule("credentials", [Signal.CREDENTIALS]),
    _rule("safe_account", [Signal.SAFE_ACCOUNT]),
    _rule(
        "authority_asks",
        [Signal.AUTHORITY],
        [Signal.MONEY_TRANSFER, Signal.PERSONAL_INFO, Signal.LINK_OR_APP],
    ),
    _rule("secret_payment", [Signal.SECRECY], [Signal.MONEY_TRANSFER, Signal.PERSONAL_INFO]),
    _rule("impostor_link", [Signal.LINK_OR_APP], [Signal.BANK, Signal.SERVICE]),
    # Paying for something too good to be true.
    _rule("easy_profit_payment", [Signal.EASY_PROFIT, Signal.MONEY_TRANSFER]),
    _rule("miracle_cure_payment", [Signal.MIRACLE_CURE, Signal.MONEY_TRANSFER]),
    _rule("prize_payment", [Signal.PRIZE, Signal.MONEY_TRANSFER]),
)


@dataclass(frozen=True)
class RuleResult:
    level: RiskLevel
    # None only when there is no signal at all.
    scam_type: ScamType | None
    signals: frozenset[Signal]
    # The decisive rule that made the level high, if any.
    decisive_rule: str | None = None

    @property
    def decisive(self) -> bool:
        return self.decisive_rule is not None


def _normalize(text: str) -> str:
    """Accent-free lower-case words, single-spaced and padded, for whole-word matching."""
    return f" {' '.join(words(text))} "


_NORMALIZED: dict[Signal, tuple[str, ...]] = {
    signal: tuple(_normalize(phrase) for phrase in phrases) for signal, phrases in PHRASES.items()
}


def find_signals(situation: str) -> frozenset[Signal]:
    text = _normalize(situation)
    return frozenset(
        signal
        for signal, phrases in _NORMALIZED.items()
        if any(phrase in text for phrase in phrases)
    )


def assess_rules(situation: str) -> RuleResult:
    signals = find_signals(situation)
    scam_type = _scam_type(signals)
    for rule in DECISIVE_RULES:
        if rule.fires(signals):
            return RuleResult(RiskLevel.HIGH, scam_type, signals, rule.name)
    return RuleResult(_level(signals), scam_type, signals)


def _level(signals: frozenset[Signal]) -> RiskLevel:
    asks, pressure, story = signals & ASKS, signals & PRESSURE, signals & STORY
    if (asks and (pressure or story)) or (pressure and story) or signals & STRONG_CLAIMS:
        return RiskLevel.MEDIUM
    if signals:
        return RiskLevel.LOW
    return RiskLevel.NONE


def _scam_type(signals: frozenset[Signal]) -> ScamType | None:
    """The type with the most cue weight; ties go to the type declared first in ScamType."""
    if not signals:
        return None
    weights: Counter[ScamType] = Counter()
    for signal in signals & STORY:
        scam_type, weight = TYPE_CUES[signal]
        weights[scam_type] += weight
    if not weights:
        # An OTP request with no story is nearly always a fake bank.
        return ScamType.BANK_IMPERSONATION if Signal.CREDENTIALS in signals else ScamType.OTHER
    order = list(ScamType)
    return max(weights, key=lambda t: (weights[t], -order.index(t)))
