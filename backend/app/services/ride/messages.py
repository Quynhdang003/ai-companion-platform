"""What the agent says about rides: short Vietnamese sentences it reads out as they are."""

import math
from collections.abc import Sequence

from app.models import CancelReason, RideBooking, RidePlaceOption, RideStatus, RideType

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


NO_RIDE = "Dạ, hiện bác không có chuyến xe nào ạ."
STATUS_UNAVAILABLE = (
    "Dạ, hệ thống đặt xe đang chậm nên con chưa xem được xe đang ở đâu."
    " Bác chờ một lát rồi hỏi lại con nhé."
)
NO_RIDE_TO_CANCEL = "Dạ, hiện bác không có chuyến xe nào để hủy ạ."
CANCEL_IN_PROGRESS = "Dạ, bác đang ở trên xe rồi nên con không hủy được chuyến này ạ."
CANCEL_UNAVAILABLE = (
    "Dạ, hệ thống đặt xe đang chậm nên con chưa hủy được. Bác chờ một lát rồi con thử lại nhé."
)


def _car(ride: RideBooking) -> str:
    """ "Toyota Vios biển số 30H-575.35", or the ride type before a driver is known."""
    if ride.driver_vehicle and ride.driver_plate:
        return f"{ride.driver_vehicle} biển số {ride.driver_plate}"
    return RIDE_TYPE_LABELS[ride.quote.ride_type]


def ride_status(ride: RideBooking, pickup_eta_s: int | None, dropoff_eta_s: int | None) -> str:
    """Where the ride is, for the elder. ETAs are live (None: not known now)."""
    pickup, destination = ride.quote.pickup.name, ride.quote.destination.name
    match ride.status:
        case RideStatus.REQUESTED:
            text = "Dạ, hệ thống đang tìm tài xế cho bác ạ."
            if pickup_eta_s is not None:
                text += f" Xe dự kiến đến đón sau khoảng {speak_duration(pickup_eta_s)}."
            return text
        case RideStatus.DRIVER_ASSIGNED:
            driver = f"tài xế {ride.driver_name}" if ride.driver_name else "tài xế"
            text = f"Dạ, {driver} đã nhận chuyến, đi {_car(ride)}."
            if pickup_eta_s is not None:
                text += f" Xe sẽ đến đón ở {pickup} sau khoảng {speak_duration(pickup_eta_s)}."
            return text
        case RideStatus.ARRIVING:
            text = f"Dạ, xe sắp đến rồi ạ, {_car(ride)}."
            if pickup_eta_s is not None:
                text += f" Còn khoảng {speak_duration(pickup_eta_s)} nữa."
            return text + f" Bác chuẩn bị ra {pickup} nhé."
        case RideStatus.IN_PROGRESS:
            text = f"Dạ, bác đang trên đường đến {destination}"
            if dropoff_eta_s is not None:
                text += f", còn khoảng {speak_duration(dropoff_eta_s)} nữa"
            return text + " ạ."
        case RideStatus.COMPLETED:
            return f"Dạ, chuyến xe đến {destination} đã hoàn thành rồi ạ."
    if ride.cancel_reason is CancelReason.DRIVER:
        return f"Dạ, tài xế đã hủy chuyến xe đi {destination}. Bác có muốn con đặt xe khác không ạ?"
    if ride.cancel_reason is CancelReason.LOST:
        return (
            f"Dạ, con không còn thấy chuyến xe đi {destination} trong hệ thống nữa."
            " Bác có muốn con đặt lại không ạ?"
        )
    return f"Dạ, chuyến xe đi {destination} đã được hủy rồi ạ."


def cancelled(ride: RideBooking) -> str:
    return f"Dạ, con đã hủy chuyến xe đi {ride.quote.destination.name} rồi ạ."


def already_cancelled(ride: RideBooking) -> str:
    if ride.cancel_reason is CancelReason.RIDER:
        return f"Dạ, chuyến xe đi {ride.quote.destination.name} đã được hủy từ trước rồi ạ."
    # Cancelled by the driver, or lost: the elder may not know yet.
    return ride_status(ride, None, None)


def cancel_completed(ride: RideBooking) -> str:
    return f"Dạ, chuyến xe đi {ride.quote.destination.name} đã hoàn thành nên không hủy được nữa ạ."
