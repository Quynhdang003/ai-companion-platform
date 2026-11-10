"""What the agent says after a scam check: short, speakable Vietnamese, from templates.

Templated rather than generated, so the warning is always the same, safe advice. The
per-type advice follows the KB scam document (`backend/data/kb/nhan-biet-cuoc-goi-lua-dao.md`).
Nothing here promises a family alert: the elder may have no family on Telegram.
"""

from app.models import RiskLevel, ScamType

ADVICE: dict[ScamType, str] = {
    ScamType.POLICE_IMPERSONATION: (
        "Công an không bao giờ làm việc hay bắt chuyển tiền qua điện thoại ạ."
    ),
    ScamType.BANK_IMPERSONATION: "Ngân hàng không bao giờ hỏi mã OTP hay mật khẩu của bác ạ.",
    ScamType.RELATIVE_IMPERSONATION: (
        "Bác nhớ gọi vào số quen của con cháu, đừng tin số lạ tự xưng là người nhà ạ."
    ),
    ScamType.INVESTMENT: "Không có khoản đầu tư nào lãi cao mà lại không có rủi ro đâu ạ.",
    ScamType.HEALTH_PRODUCT: "Bác chỉ nên dùng thuốc theo đơn của bác sĩ khám trực tiếp thôi ạ.",
    ScamType.RESORT_CONTRACT: "Bác đừng ký hợp đồng hay trả trước khoản tiền nào cho họ ạ.",
    ScamType.FAKE_CHARITY: "Bác chỉ nên ủng hộ qua tổ chức quen biết, có địa chỉ rõ ràng thôi ạ.",
    ScamType.OTHER: "Nếu cần, bác gọi thẳng số tổng đài chính thức để hỏi lại ạ.",
}

_HIGH = (
    "Dạ, chuyện này rất có thể là lừa đảo ạ. Bác đừng chuyển tiền, đừng đọc mã số hay "
    "thông tin gì cho họ, gác máy rồi gọi cho con cháu nhé."
)
_MEDIUM = "Dạ, chuyện này có dấu hiệu lừa đảo ạ. Bác khoan làm theo họ, hỏi con cháu trước đã nhé."
_LOW = (
    "Dạ, con chưa thấy dấu hiệu lừa đảo rõ ràng, nhưng bác cứ cẩn thận, đừng chuyển tiền "
    "hay đọc mã số cho người lạ nhé."
)
_NONE = (
    "Dạ, con chưa thấy dấu hiệu lừa đảo trong chuyện này ạ. Nếu có ai đòi tiền hay hỏi "
    "mã số thì bác kể con nghe nhé."
)


def warning_message(level: RiskLevel, scam_type: ScamType | None) -> str:
    if level is RiskLevel.HIGH or level is RiskLevel.MEDIUM:
        lead = _HIGH if level is RiskLevel.HIGH else _MEDIUM
        return f"{lead} {ADVICE[scam_type or ScamType.OTHER]}"
    return _LOW if level is RiskLevel.LOW else _NONE
