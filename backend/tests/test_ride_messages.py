import pytest

from app.models import PlaceSource, RidePlaceOption
from app.services.ride.messages import places_found, speak_duration, speak_price, whole_minutes


@pytest.mark.parametrize(
    ("vnd", "spoken"),
    [
        (72_000, "72 nghìn đồng"),
        (8_000, "8 nghìn đồng"),
        (130_000, "130 nghìn đồng"),
        (1_000_000, "1 triệu đồng"),
        (1_250_000, "1 triệu 250 nghìn đồng"),
        (2_005_000, "2 triệu 5 nghìn đồng"),
    ],
)
def test_prices_are_said_in_thousands(vnd: int, spoken: str) -> None:
    assert speak_price(vnd) == spoken


@pytest.mark.parametrize(
    ("seconds", "spoken"),
    [
        (0, "1 phút"),
        (59, "1 phút"),
        (60, "1 phút"),
        (61, "2 phút"),
        (799, "14 phút"),
        (3_600, "1 tiếng"),
        (4_500, "1 tiếng 15 phút"),
    ],
)
def test_durations_are_rounded_up_to_minutes(seconds: int, spoken: str) -> None:
    assert speak_duration(seconds) == spoken


def test_whole_minutes_is_never_zero() -> None:
    assert [whole_minutes(s) for s in (0, 30, 60, 61, 283)] == [1, 1, 1, 2, 5]


def _option(name: str, address: str = "") -> RidePlaceOption:
    return RidePlaceOption(
        ref=1, name=name, address=address, lat=21.0, lng=105.8, source=PlaceSource.PROVIDER
    )


def test_one_place_found_is_asked_about() -> None:
    assert places_found([_option("Bệnh viện Bạch Mai", "78 Đường Giải Phóng")]) == (
        "Dạ, con tìm được Bệnh viện Bạch Mai, 78 Đường Giải Phóng. Có phải chỗ này không ạ?"
    )


def test_several_places_found_are_listed() -> None:
    options = [_option("Chợ Hôm", "79 Phố Huế"), _option("Ngõ 12 Phố Láng Hạ")]

    assert places_found(options) == (
        "Dạ, con tìm được mấy chỗ: Chợ Hôm, 79 Phố Huế; Ngõ 12 Phố Láng Hạ. Bác muốn chỗ nào ạ?"
    )
