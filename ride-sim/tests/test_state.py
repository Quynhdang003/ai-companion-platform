from datetime import UTC, datetime, timedelta

import pytest

from app.models import RideStatus
from app.state import plan_timeline, status_at

T0 = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def test_timeline_of_a_ride() -> None:
    # Accepted after 20 s, 300 s to the pickup, a 900 s trip.
    timeline = plan_timeline(T0, pickup_duration_s=300, trip_duration_s=900, time_scale=1)

    assert timeline.requested_at == T0
    assert timeline.assigned_at == _at(20)
    assert timeline.arriving_at == _at(200)  # 120 s before the pickup
    assert timeline.pickup_at == _at(320)
    assert timeline.dropoff_at == _at(1220)


def test_time_scale_shortens_real_time() -> None:
    timeline = plan_timeline(T0, pickup_duration_s=300, trip_duration_s=900, time_scale=30)

    assert timeline.assigned_at == _at(20 / 30)
    assert timeline.pickup_at == _at(320 / 30)
    assert timeline.dropoff_at == _at(1220 / 30)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, RideStatus.REQUESTED),
        (19, RideStatus.REQUESTED),
        (20, RideStatus.DRIVER_ASSIGNED),
        (199, RideStatus.DRIVER_ASSIGNED),
        (200, RideStatus.ARRIVING),
        (319, RideStatus.ARRIVING),
        (320, RideStatus.IN_PROGRESS),
        (1219, RideStatus.IN_PROGRESS),
        (1220, RideStatus.COMPLETED),
        (99_999, RideStatus.COMPLETED),
    ],
)
def test_status_follows_the_clock(seconds: int, expected: RideStatus) -> None:
    timeline = plan_timeline(T0, pickup_duration_s=300, trip_duration_s=900, time_scale=1)

    assert status_at(_at(seconds), timeline, None) is expected


def test_a_driver_close_by_is_arriving_as_soon_as_assigned() -> None:
    timeline = plan_timeline(T0, pickup_duration_s=60, trip_duration_s=900, time_scale=1)

    assert timeline.arriving_at == timeline.assigned_at
    assert status_at(_at(19), timeline, None) is RideStatus.REQUESTED
    assert status_at(_at(20), timeline, None) is RideStatus.ARRIVING


def test_cancelled_from_the_cancel_time_on() -> None:
    timeline = plan_timeline(T0, pickup_duration_s=300, trip_duration_s=900, time_scale=1)
    cancelled_at = _at(100)

    assert status_at(_at(99), timeline, cancelled_at) is RideStatus.DRIVER_ASSIGNED
    assert status_at(_at(100), timeline, cancelled_at) is RideStatus.CANCELLED
    # Still cancelled when the ride would have ended.
    assert status_at(_at(5_000), timeline, cancelled_at) is RideStatus.CANCELLED
