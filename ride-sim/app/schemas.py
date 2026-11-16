from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field

from app.config import Fault
from app.geo import Point
from app.geocoding import Place
from app.models import CancelReason, Quote, RideStatus, RideType
from app.simulator import BookingView, SimConfig


class PointModel(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

    def to_point(self) -> Point:
        return Point(self.lat, self.lng)

    @classmethod
    def from_point(cls, point: Point) -> Self:
        return cls(lat=point.lat, lng=point.lng)


class QuoteRequest(BaseModel):
    pickup: PointModel
    destination: PointModel
    ride_type: RideType


class QuoteOut(BaseModel):
    id: str
    ride_type: RideType
    pickup: PointModel
    destination: PointModel
    distance_m: int
    # Travel time of the trip, in seconds.
    duration_s: int
    price_vnd: int
    # Peak-hour price.
    peak: bool
    # Priced higher than usual (`price_surge` fault).
    surge: bool
    # Distance and duration are a straight-line estimate, not a road route.
    estimated: bool
    # Seconds until a driver would reach the pickup; null when no driver is near.
    pickup_eta_s: int | None
    expires_at: datetime

    @classmethod
    def from_quote(cls, quote: Quote) -> Self:
        return cls(
            id=quote.id,
            ride_type=quote.ride_type,
            pickup=PointModel.from_point(quote.pickup),
            destination=PointModel.from_point(quote.destination),
            distance_m=quote.distance_m,
            duration_s=quote.duration_s,
            price_vnd=quote.price_vnd,
            peak=quote.peak,
            surge=quote.surge,
            estimated=quote.estimated,
            pickup_eta_s=quote.pickup_eta_s,
            expires_at=quote.expires_at,
        )


class BookingRequest(BaseModel):
    quote_id: str = Field(min_length=1, max_length=64)


class DriverOut(BaseModel):
    name: str
    vehicle: str
    plate: str


class BookingOut(BaseModel):
    id: str
    quote_id: str
    status: RideStatus
    ride_type: RideType
    pickup: PointModel
    destination: PointModel
    distance_m: int
    duration_s: int
    price_vnd: int
    # Null until a driver has accepted.
    driver: DriverOut | None
    # Seconds until the driver reaches the pickup; null once the passenger is on board.
    pickup_eta_s: int | None
    # Seconds until the drop-off; null once the ride is completed or cancelled.
    dropoff_eta_s: int | None
    requested_at: datetime
    cancelled_at: datetime | None
    cancel_reason: CancelReason | None

    @classmethod
    def from_view(cls, view: BookingView) -> Self:
        booking, quote, driver = view.booking, view.booking.quote, view.driver
        cancelled = view.status is RideStatus.CANCELLED
        return cls(
            id=booking.id,
            quote_id=booking.quote_id,
            status=view.status,
            ride_type=quote.ride_type,
            pickup=PointModel.from_point(quote.pickup),
            destination=PointModel.from_point(quote.destination),
            distance_m=quote.distance_m,
            duration_s=quote.duration_s,
            price_vnd=quote.price_vnd,
            driver=(
                None
                if driver is None
                else DriverOut(name=driver.name, vehicle=driver.vehicle, plate=driver.plate)
            ),
            pickup_eta_s=view.pickup_eta_s,
            dropoff_eta_s=view.dropoff_eta_s,
            requested_at=booking.requested_at,
            cancelled_at=booking.cancelled_at if cancelled else None,
            cancel_reason=booking.cancel_reason if cancelled else None,
        )


class PlaceOut(BaseModel):
    name: str
    # Street address when known, else "".
    address: str
    lat: float
    lng: float
    # "builtin" (the simulator's own list) or "photon".
    source: str

    @classmethod
    def from_place(cls, place: Place) -> Self:
        return cls(
            name=place.name,
            address=place.address,
            lat=place.location.lat,
            lng=place.location.lng,
            source=place.source,
        )


class SimConfigOut(BaseModel):
    time_scale: float
    fault: Fault | None

    @classmethod
    def from_config(cls, config: SimConfig) -> Self:
        return cls(time_scale=config.time_scale, fault=config.fault)


class SimConfigPatch(BaseModel):
    """Only the fields sent are changed; `"fault": null` turns the fault off."""

    time_scale: float | None = Field(default=None, gt=0)
    fault: Fault | None = None
