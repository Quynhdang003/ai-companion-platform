"""The ride state machine, read off timestamps.

    REQUESTED -> DRIVER_ASSIGNED -> ARRIVING -> IN_PROGRESS -> COMPLETED
        any state before IN_PROGRESS -> CANCELLED

Nothing moves a booking along: the real time of every step is fixed when it is booked
(`plan_timeline`) and the status is whatever step the clock has reached (`status_at`).
Durations are in simulated seconds; `time_scale` simulated seconds pass per real second.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models import RideStatus

# Simulated seconds until a driver accepts the request.
ASSIGN_DELAY_S = 20
# The driver counts as arriving for this long before reaching the pickup.
ARRIVING_WINDOW_S = 120

# Under the `driver_cancels` fault the driver gives up this long after accepting: always
# before the pickup, which is at least a minute away (`MIN_PICKUP_DURATION_S`).
DRIVER_CANCEL_DELAY_S = 45

# A ride can be cancelled until the passenger is on board.
CANCELLABLE = frozenset({RideStatus.REQUESTED, RideStatus.DRIVER_ASSIGNED, RideStatus.ARRIVING})


@dataclass(frozen=True)
class Timeline:
    requested_at: datetime
    assigned_at: datetime
    arriving_at: datetime
    pickup_at: datetime
    dropoff_at: datetime


def plan_timeline(
    requested_at: datetime, *, pickup_duration_s: int, trip_duration_s: int, time_scale: float
) -> Timeline:
    """`pickup_duration_s`: the driver's way to the pickup; `trip_duration_s`: the trip."""

    def after(simulated_seconds: float) -> datetime:
        return requested_at + timedelta(seconds=simulated_seconds / time_scale)

    pickup_after = ASSIGN_DELAY_S + pickup_duration_s
    return Timeline(
        requested_at=requested_at,
        assigned_at=after(ASSIGN_DELAY_S),
        # A driver who starts close by is arriving as soon as the request is accepted.
        arriving_at=after(max(ASSIGN_DELAY_S, pickup_after - ARRIVING_WINDOW_S)),
        pickup_at=after(pickup_after),
        dropoff_at=after(pickup_after + trip_duration_s),
    )


def driver_cancel_time(timeline: Timeline, time_scale: float) -> datetime:
    return timeline.assigned_at + timedelta(seconds=DRIVER_CANCEL_DELAY_S / time_scale)


def status_at(now: datetime, timeline: Timeline, cancelled_at: datetime | None) -> RideStatus:
    if cancelled_at is not None and now >= cancelled_at:
        return RideStatus.CANCELLED
    if now >= timeline.dropoff_at:
        return RideStatus.COMPLETED
    if now >= timeline.pickup_at:
        return RideStatus.IN_PROGRESS
    if now >= timeline.arriving_at:
        return RideStatus.ARRIVING
    if now >= timeline.assigned_at:
        return RideStatus.DRIVER_ASSIGNED
    return RideStatus.REQUESTED
