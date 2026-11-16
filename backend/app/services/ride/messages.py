"""What the agent says about rides: short Vietnamese sentences it reads out as they are."""

import math
from collections.abc import Sequence

from app.models import RidePlaceOption, RideType

RIDE_TYPE_LABELS = {
    RideType.BIKE: "xe máy",
    RideType.CAR4: "xe bốn chỗ",
    RideType.CAR7: "xe bảy chỗ",
}

NOT_ACTIVE = "Dạ, con chỉ đặt xe được cho người đã đăng ký và đồng ý dùng dịch vụ ạ."
UNKNOWN_PLACE = (
    "Dạ, con chưa rõ bác muốn đi từ đâu đến đâu. Bác nói lại điểm đón và điểm đến giúp con nhé."
)
CONFIRMATION_REQUIRED = (
    "Dạ, bác nghe giá xong và đồng ý thì con mới đặt xe ạ. Bác có đồng ý đặt xe không ạ?"
)

PLACE_NOT_FOUND = (
    "Dạ, con chưa tìm thấy chỗ này. Bác nói rõ hơn tên đường hoặc tên địa điểm giúp con nhé."
)
PLACES_UNAVAILABLE = "Dạ, hệ thống tìm địa điểm đang chậm. Bác chờ một lát rồi con tìm lại nhé."

OUT_OF_AREA = "Dạ, con chỉ đặt được xe đi trong Hà Nội thôi ạ."
TOO_SHORT = "Dạ, điểm đón và điểm đến gần như cùng một chỗ. Bác kiểm tra lại giúp con nhé."
QUOTE_UNAVAILABLE = (
    "Dạ, hệ thống đặt xe đang chậm nên con chưa báo giá được. Bác chờ một lát rồi con thử lại nhé."
)

NO_QUOTE = "Dạ, con chưa báo giá loại xe này. Con báo giá trước rồi bác quyết định nhé."
QUOTE_EXPIRED = "Dạ, giá con báo lúc nãy đã hết hạn. Con báo giá lại cho bác nhé."
BOOK_UNAVAILABLE = (
    "Dạ, hệ thống đặt xe đang chậm nên con chưa đặt được. Bác chờ một lát rồi con thử lại nhé."
)


def speak_price(vnd: int) -> str:
    """72000 -> "72 nghìn đồng"; 1250000 -> "1 triệu 250 nghìn đồng"."""
    millions, thousands = divmod(round(vnd / 1000), 1000)
    parts = []
    if millions:
        parts.append(f"{millions} triệu")
    if thousands or not millions:
        parts.append(f"{thousands} nghìn")
    return " ".join(parts) + " đồng"


def whole_minutes(seconds: int) -> int:
    """Rounded up, at least 1: a wait is never "0 minutes"."""
    return max(1, math.ceil(seconds / 60))


def speak_duration(seconds: int) -> str:
    """799 -> "14 phút"; 4500 -> "1 tiếng 15 phút"."""
    hours, minutes = divmod(whole_minutes(seconds), 60)
    if not hours:
        return f"{minutes} phút"
    return f"{hours} tiếng" + (f" {minutes} phút" if minutes else "")


def speak_place(option: RidePlaceOption) -> str:
    if option.address and option.address != option.name:
        return f"{option.name}, {option.address}"
    return option.name


def places_found(options: Sequence[RidePlaceOption]) -> str:
    if len(options) == 1:
        return f"Dạ, con tìm được {speak_place(options[0])}. Có phải chỗ này không ạ?"
    listed = "; ".join(speak_place(option) for option in options)
    return f"Dạ, con tìm được mấy chỗ: {listed}. Bác muốn chỗ nào ạ?"


def quoted(
    ride_type: RideType,
    pickup: RidePlaceOption,
    destination: RidePlaceOption,
    *,
    price_vnd: int,
    trip_s: int,
    pickup_eta_s: int,
    surge: bool,
) -> str:
    text = (
        f"Dạ, {RIDE_TYPE_LABELS[ride_type]} từ {pickup.name} đến {destination.name}"
        f" hết khoảng {speak_price(price_vnd)}, đi mất khoảng {speak_duration(trip_s)}."
        f" Xe đến đón sau khoảng {speak_duration(pickup_eta_s)}."
    )
    if surge:
        text += " Giá lúc này đang cao hơn bình thường."
    return text + " Bác có đồng ý đặt xe không ạ?"


def no_driver(ride_type: RideType) -> str:
    return (
        f"Dạ, lúc này không có {RIDE_TYPE_LABELS[ride_type]} nào ở gần điểm đón."
        " Bác muốn thử loại xe khác hay đợi một lát ạ?"
    )


def booked(ride_type: RideType, pickup: RidePlaceOption, pickup_eta_s: int | None) -> str:
    text = f"Dạ, con đã đặt {RIDE_TYPE_LABELS[ride_type]} cho bác rồi ạ."
    if pickup_eta_s is not None:
        text += f" Xe sẽ đến đón ở {pickup.name} sau khoảng {speak_duration(pickup_eta_s)}."
    return text
