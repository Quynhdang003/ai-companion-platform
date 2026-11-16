"""What booking a ride needs from a ride provider, whoever it is (`RideProvider`).

The ride simulator is the only provider (`simulator.py`); tests use `FakeRideProvider`
(`tests/fakes.py`).
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models import RideStatus, RideType

# Error codes a provider refuses a request with (`RideRequestRefusedError.code`).
OUT_OF_SERVICE_AREA = "out_of_service_area"
TRIP_TOO_SHORT = "trip_too_short"
QUOTE_EXPIRED = "quote_expired"
QUOTE_NOT_FOUND = "quote_not_found"
NO_DRIVER_AVAILABLE = "no_driver_available"
BOOKING_NOT_FOUND = "booking_not_found"
RIDE_IN_PROGRESS = "ride_in_progress"
RIDE_COMPLETED = "ride_completed"

_EARTH_RADIUS_M = 6_371_000


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lng: float


def distance_m(a: GeoPoint, b: GeoPoint) -> float:
    """Straight-line distance over the Earth's surface."""
    lat_a, lat_b = math.radians(a.lat), math.radians(b.lat)
    d_lat, d_lng = lat_b - lat_a, math.radians(b.lng - a.lng)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lng / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class ProviderPlace:
    name: str
    # Street address when known, else "".
    address: str
    location: GeoPoint


@dataclass(frozen=True)
class ProviderQuote:
    id: str
    ride_type: RideType
    price_vnd: int
    distance_m: int
    # The trip itself, in seconds.
    duration_s: int
    # Until the nearest driver would reach the pickup; None when no driver is near.
    pickup_eta_s: int | None
    surge: bool
    expires_at: datetime


@dataclass(frozen=True)
class ProviderDriver:
    name: str
    vehicle: str
    plate: str


@dataclass(frozen=True)
class ProviderBooking:
    id: str
    quote_id: str
    status: RideStatus
    # None until a driver accepted.
    driver: ProviderDriver | None
    # Seconds left; None once they no longer apply.
    pickup_eta_s: int | None
    dropoff_eta_s: int | None
    # "rider" or "driver" once cancelled.
    cancel_reason: str | None = None


class RideProviderError(Exception):
    """The provider didn't do what was asked."""


class RideProviderUnavailableError(RideProviderError):
    """No usable answer: unreachable, too slow, failing, or an unexpected body.

    The request may or may not have been carried out; asking again is safe (a quote is
    booked at most once).
    """


class RideRequestRefusedError(RideProviderError):
    """The provider answered and refused; `code` says why (the constants above)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RideProvider(Protocol):
    async def search_places(self, query: str, limit: int) -> list[ProviderPlace]:
        """Places matching `query`, best first; [] when none match."""
        ...

    async def quote(
        self, ride_type: RideType, pickup: GeoPoint, destination: GeoPoint
    ) -> ProviderQuote: ...

    async def book(self, quote_id: str) -> ProviderBooking:
        """Book a quote; booking it again returns the same booking."""
        ...

    async def get_booking(self, booking_id: str) -> ProviderBooking:
        """The booking as it is now."""
        ...

    async def cancel(self, booking_id: str) -> ProviderBooking:
        """Cancel for the rider; cancelling a cancelled ride changes nothing. Refused once
        the passenger is on board (`RIDE_IN_PROGRESS`) or the ride is over."""
        ...
