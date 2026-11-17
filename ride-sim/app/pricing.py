"""Fares: base + per kilometre + per minute by ride type, more at peak hours."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from app.models import RideType

# Vietnam has no daylight saving time, so a fixed offset is enough (and needs no tz database).
VIETNAM_TZ = timezone(timedelta(hours=7))


@dataclass(frozen=True)
class Fare:
    base_vnd: int
    per_km_vnd: int
    per_minute_vnd: int


FARES: dict[RideType, Fare] = {
    RideType.BIKE: Fare(base_vnd=8_000, per_km_vnd=3_800, per_minute_vnd=200),
    RideType.CAR4: Fare(base_vnd=20_000, per_km_vnd=11_000, per_minute_vnd=500),
    RideType.CAR7: Fare(base_vnd=25_000, per_km_vnd=13_000, per_minute_vnd=600),
}

PEAK_MULTIPLIER = 1.3
# Vietnam time, every day; the end of each range is not peak any more.
PEAK_HOURS: tuple[tuple[time, time], ...] = (
    (time(7, 0), time(9, 0)),
    (time(17, 0), time(19, 30)),
)
# Prices are whole thousands of dong: easy to say.
ROUND_TO_VND = 1_000


def is_peak(at: datetime) -> bool:
    local = at.astimezone(VIETNAM_TZ).time()
    return any(start <= local < end for start, end in PEAK_HOURS)


def price_vnd(
    ride_type: RideType, distance_m: int, duration_s: int, *, peak: bool, surge: float = 1.0
) -> int:
    """`surge` multiplies the price on top of the peak multiplier."""
    fare = FARES[ride_type]
    price = (
        fare.base_vnd + fare.per_km_vnd * distance_m / 1000 + fare.per_minute_vnd * duration_s / 60
    )
    if peak:
        price *= PEAK_MULTIPLIER
    price *= surge
    return int(price / ROUND_TO_VND + 0.5) * ROUND_TO_VND
