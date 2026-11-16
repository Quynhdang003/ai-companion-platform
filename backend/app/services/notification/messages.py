"""Text of the messages sent to family members (plain text, Vietnamese).

A scam alert names the elder and gives the scam type, risk level and time; a ride update
gives what the elder chose to share (`ride_share_scope`). Never anything said in a call
(architecture invariant 9).
"""

from datetime import datetime, timedelta, timezone

from app.models import (
    CancelReason,
    RideBooking,
    RideEvent,
    RidePlaceOption,
    RideShareScope,
    RiskLevel,
    ScamType,
)
from app.services.ride.messages import RIDE_TYPE_LABELS

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


RIDE_EVENT_LABELS: dict[RideEvent, str] = {
    RideEvent.BOOKED: "Đã đặt xe",
    RideEvent.ON_THE_WAY: "Đã lên xe, đang trên đường",
    RideEvent.ARRIVED: "Đã đến nơi",
    RideEvent.CANCELLED: "Chuyến xe đã bị hủy",
}

CANCELLED_BY_LABELS: dict[CancelReason, str] = {
    CancelReason.RIDER: "Người thân của bạn (qua trợ lý)",
    CancelReason.DRIVER: "Tài xế",
}

STATUS_ONLY_NOTE = "Người thân của bạn chọn chỉ chia sẻ trạng thái chuyến đi, không kèm địa điểm."


def _place(option: RidePlaceOption) -> str:
    if option.address and option.address != option.name:
        return f"{option.name} ({option.address})"
    return option.name


def ride_update(
    elder_name: str, event: RideEvent, at: datetime, ride: RideBooking, scope: RideShareScope
) -> str:
    """A ride update within the elder's scope: `status` or `details` (never sent for `none`)."""
    when = at.astimezone(VN_TZ).strftime("%H:%M ngày %d/%m/%Y")
    lines = [
        f"🚕 Chuyến xe: {RIDE_EVENT_LABELS[event]}",
        f"Người thân: {elder_name}",
        f"Loại xe: {RIDE_TYPE_LABELS[ride.quote.ride_type].capitalize()}",
        f"Thời gian: {when}",
    ]
    if event is RideEvent.CANCELLED and ride.cancel_reason in CANCELLED_BY_LABELS:
        lines.append(f"Người hủy: {CANCELLED_BY_LABELS[ride.cancel_reason]}")
    if scope is not RideShareScope.DETAILS:
        return "\n".join(lines) + "\n\n" + STATUS_ONLY_NOTE
    lines += [
        f"Điểm đón: {_place(ride.quote.pickup)}",
        f"Điểm đến: {_place(ride.quote.destination)}",
    ]
    if ride.driver_vehicle and ride.driver_plate:
        lines.append(f"Xe: {ride.driver_vehicle}, biển số {ride.driver_plate}")
    return "\n".join(lines)
