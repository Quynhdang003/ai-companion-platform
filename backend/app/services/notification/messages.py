"""Text of the messages sent to family members (plain text, Vietnamese).

A scam alert names the elder and gives the scam type, risk level and time: never anything
said in the call (architecture invariant 9).
"""

from datetime import datetime, timedelta, timezone

from app.models import RiskLevel, ScamType

VN_TZ = timezone(timedelta(hours=7))

# Same names as the sections of the KB scam doc (`data/kb/nhan-biet-cuoc-goi-lua-dao.md`).
SCAM_TYPE_LABELS: dict[ScamType, str] = {
    ScamType.POLICE_IMPERSONATION: "Giả danh công an, viện kiểm sát, tòa án",
    ScamType.BANK_IMPERSONATION: "Giả danh nhân viên ngân hàng",
    ScamType.RELATIVE_IMPERSONATION: "Giả danh con cháu hoặc người quen",
    ScamType.INVESTMENT: "Mời đầu tư lãi cao",
    ScamType.HEALTH_PRODUCT: "Bán thuốc, thực phẩm chức năng",
    ScamType.RESORT_CONTRACT: "Hợp đồng du lịch, nghỉ dưỡng",
    ScamType.FAKE_CHARITY: "Kêu gọi từ thiện giả",
    ScamType.OTHER: "Kiểu lừa đảo khác",
}

RISK_LEVEL_LABELS: dict[RiskLevel, str] = {
    RiskLevel.HIGH: "Cao",
    RiskLevel.MEDIUM: "Trung bình",
    RiskLevel.LOW: "Thấp",
    RiskLevel.NONE: "Không có",
}


def scam_alert(elder_name: str, scam_type: ScamType, level: RiskLevel, at: datetime) -> str:
    when = at.astimezone(VN_TZ).strftime("%H:%M ngày %d/%m/%Y")
    return (
        "⚠️ Cảnh báo lừa đảo\n"
        f"Người thân: {elder_name}\n"
        f"Kiểu lừa đảo: {SCAM_TYPE_LABELS[scam_type]}\n"
        f"Mức nguy cơ: {RISK_LEVEL_LABELS[level]}\n"
        f"Thời gian: {when}\n\n"
        "Trợ lý đã cảnh báo người thân của bạn trong cuộc gọi. Bạn nên gọi lại ngay để hỏi "
        "thăm, và nhắc không chuyển tiền hay đọc mã số cho người lạ."
    )
