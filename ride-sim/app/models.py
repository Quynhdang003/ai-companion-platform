import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UtcDateTime
from app.geo import Point


class RideType(StrEnum):
    BIKE = "bike"  # motorbike, one passenger
    CAR4 = "car4"
    CAR7 = "car7"


class RideStatus(StrEnum):
    """Where a booking is, computed from its timestamps (`app/state.py`)."""

    REQUESTED = "REQUESTED"  # looking for a driver
    DRIVER_ASSIGNED = "DRIVER_ASSIGNED"  # a driver accepted and is on the way
    ARRIVING = "ARRIVING"  # the driver is about to reach the pickup
    IN_PROGRESS = "IN_PROGRESS"  # passenger on board
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CancelReason(StrEnum):
    RIDER = "rider"
    DRIVER = "driver"  # only under the `driver_cancels` fault


def _new_id() -> str:
    return uuid.uuid4().hex


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


class Quote(Base):
    """A price for one trip, bookable until `expires_at`."""

    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    ride_type: Mapped[RideType] = mapped_column(
        Enum(RideType, native_enum=False, values_callable=_values)
    )
    pickup_lat: Mapped[float]
    pickup_lng: Mapped[float]
    destination_lat: Mapped[float]
    destination_lng: Mapped[float]
    distance_m: Mapped[int]
    # Travel time of the trip itself, in simulated seconds.
    duration_s: Mapped[int]
    price_vnd: Mapped[int]
    # Priced with the peak-hour multiplier.
    peak: Mapped[bool]
    # Priced with the surge multiplier (`price_surge` fault).
    surge: Mapped[bool]
    # Distance and duration don't come from a road network.
    estimated: Mapped[bool]
    # Simulated seconds until a driver would reach the pickup; None when no driver is near.
    pickup_eta_s: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)

    @property
    def pickup(self) -> Point:
        return Point(self.pickup_lat, self.pickup_lng)

    @property
    def destination(self) -> Point:
        return Point(self.destination_lat, self.destination_lng)


class Booking(Base):
    """A booked quote. Its status isn't stored: the times below are fixed when it is booked
    and the status is read off them (`app/state.py`)."""

    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    # One booking per quote: booking the same quote again returns this row.
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), unique=True)
    # A driver from `app/dispatch.py` (generated from the seed, not stored).
    driver_id: Mapped[str] = mapped_column(String(8), index=True)
    # Simulated seconds per real second when it was booked; turns real time left into ETAs.
    time_scale: Mapped[float]
    # Real times the booking moves on at.
    requested_at: Mapped[datetime] = mapped_column(UtcDateTime)
    assigned_at: Mapped[datetime] = mapped_column(UtcDateTime)
    arriving_at: Mapped[datetime] = mapped_column(UtcDateTime)
    pickup_at: Mapped[datetime] = mapped_column(UtcDateTime)
    dropoff_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # Cancelled from this time on.
    cancelled_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    cancel_reason: Mapped[CancelReason | None] = mapped_column(
        Enum(CancelReason, native_enum=False, values_callable=_values)
    )

    quote: Mapped[Quote] = relationship(lazy="joined")
