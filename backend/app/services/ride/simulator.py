"""The ride simulator (`ride-sim/`) as the ride provider, over its REST API.

Its contract is in `context/api-contracts.md` ("Ride Simulator API"). Nothing here logs a
query or coordinates: they can tell where an elder lives.
"""

from datetime import datetime
from functools import lru_cache
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.core.config import get_settings
from app.models import RideStatus, RideType
from app.services.ride.provider import (
    GeoPoint,
    ProviderBooking,
    ProviderDriver,
    ProviderPlace,
    ProviderQuote,
    RideProviderUnavailableError,
    RideRequestRefusedError,
)

T = TypeVar("T")


class _Place(BaseModel):
    name: str
    address: str
    lat: float
    lng: float


class _Quote(BaseModel):
    id: str
    ride_type: RideType
    price_vnd: int
    distance_m: int
    duration_s: int
    pickup_eta_s: int | None
    surge: bool
    expires_at: datetime


class _Driver(BaseModel):
    name: str
    vehicle: str
    plate: str


class _Booking(BaseModel):
    id: str
    quote_id: str
    status: RideStatus
    driver: _Driver | None
    pickup_eta_s: int | None
    dropoff_eta_s: int | None


class SimRideProvider:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    async def search_places(self, query: str, limit: int) -> list[ProviderPlace]:
        body = await self._request("GET", "/places/search", params={"q": query, "limit": limit})
        places = _parse(_PLACES, body)
        return [
            ProviderPlace(name=p.name, address=p.address, location=GeoPoint(p.lat, p.lng))
            for p in places
        ]

    async def quote(
        self, ride_type: RideType, pickup: GeoPoint, destination: GeoPoint
    ) -> ProviderQuote:
        body = await self._request(
            "POST",
            "/quotes",
            json={
                "ride_type": ride_type.value,
                "pickup": {"lat": pickup.lat, "lng": pickup.lng},
                "destination": {"lat": destination.lat, "lng": destination.lng},
            },
        )
        quote = _parse(_QUOTE, body)
        return ProviderQuote(**quote.model_dump())

    async def book(self, quote_id: str) -> ProviderBooking:
        body = await self._request("POST", "/bookings", json={"quote_id": quote_id})
        booking = _parse(_BOOKING, body)
        driver = booking.driver
        return ProviderBooking(
            id=booking.id,
            quote_id=booking.quote_id,
            status=booking.status,
            driver=None if driver is None else ProviderDriver(**driver.model_dump()),
            pickup_eta_s=booking.pickup_eta_s,
            dropoff_eta_s=booking.dropoff_eta_s,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            # `from None`: a chained httpx error would show the URL, query included.
            raise RideProviderUnavailableError(f"{path}: {type(exc).__name__}") from None
        if response.status_code >= 500:
            raise RideProviderUnavailableError(f"{path}: HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise RideProviderUnavailableError(f"{path}: not JSON") from None
        if response.status_code >= 400:
            error = body.get("error") if isinstance(body, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            raise RideRequestRefusedError(
                code if isinstance(code, str) else f"http_{response.status_code}"
            )
        return body


_PLACES = TypeAdapter(list[_Place])
_QUOTE = TypeAdapter(_Quote)
_BOOKING = TypeAdapter(_Booking)


def _parse(adapter: TypeAdapter[T], body: Any) -> T:
    try:
        return adapter.validate_python(body)
    except ValidationError:
        raise RideProviderUnavailableError("unexpected response body") from None


@lru_cache
def get_ride_provider() -> SimRideProvider:
    settings = get_settings()
    return SimRideProvider(settings.ride_sim_base_url, settings.ride_provider_timeout_seconds)
