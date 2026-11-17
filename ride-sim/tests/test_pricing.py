from datetime import UTC, datetime, timedelta

import pytest

from app.models import RideType
from app.pricing import is_peak, price_vnd


@pytest.mark.parametrize(
    ("ride_type", "expected"),
    [
        # 5 km in 15 minutes: base + 5 x per km + 15 x per minute
        (RideType.BIKE, 30_000),  # 8,000 + 19,000 + 3,000
        (RideType.CAR4, 83_000),  # 20,000 + 55,000 + 7,500 = 82,500
        (RideType.CAR7, 99_000),  # 25,000 + 65,000 + 9,000
    ],
)
def test_price_is_base_plus_distance_plus_time(ride_type: RideType, expected: int) -> None:
    assert price_vnd(ride_type, 5_000, 900, peak=False) == expected


def test_peak_price_is_multiplied_before_rounding() -> None:
    # 82,500 x 1.3 = 107,250
    assert price_vnd(RideType.CAR4, 5_000, 900, peak=True) == 107_000


def test_price_is_rounded_to_the_nearest_thousand() -> None:
    # 8,000 + 2.5 min x 200 = 8,500: half goes up
    assert price_vnd(RideType.BIKE, 0, 150, peak=False) == 9_000
    # 8,000 + 2 min x 200 = 8,400
    assert price_vnd(RideType.BIKE, 0, 120, peak=False) == 8_000


@pytest.mark.parametrize(
    ("vietnam_time", "expected"),
    [
        ((6, 59), False),
        ((7, 0), True),
        ((8, 59), True),
        ((9, 0), False),
        ((12, 0), False),
        ((17, 0), True),
        ((19, 29), True),
        ((19, 30), False),
    ],
)
def test_peak_hours_are_in_vietnam_time(vietnam_time: tuple[int, int], expected: bool) -> None:
    hour, minute = vietnam_time
    # The clock runs in UTC; Vietnam is 7 hours ahead.
    at = datetime(2026, 11, 16, hour, minute, tzinfo=UTC) - timedelta(hours=7)

    assert is_peak(at) is expected
