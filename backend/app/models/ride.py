import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RideType(StrEnum):
    BIKE = "bike"  # motorbike, one passenger
    CAR4 = "car4"
    CAR7 = "car7"


class RideStatus(StrEnum):
    """Where a booking is at the ride provider, as last seen."""

    REQUESTED = "REQUESTED"  # looking for a driver
    DRIVER_ASSIGNED = "DRIVER_ASSIGNED"
    ARRIVING = "ARRIVING"
    IN_PROGRESS = "IN_PROGRESS"  # passenger on board
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


FINISHED = frozenset({RideStatus.COMPLETED, RideStatus.CANCELLED})


class CancelReason(StrEnum):
    RIDER = "rider"  # the elder, through the agent
    DRIVER = "driver"
    LOST = "lost"  # the provider no longer knows the booking (e.g. the simulator was reset)


class PlaceSource(StrEnum):
    PREVIOUS = "previous"  # a place of one of the elder's earlier rides
    PROVIDER = "provider"  # the ride provider's place search


def _str_enum(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda e: [m.value for m in e],
    )


class RidePlaceOption(Base):
    """A place `search_location` offered during a call, numbered within the call.

    The agent picks places by `ref` only, so coordinates never pass through the LLM.
    """

    __tablename__ = "ride_place_options"
    __table_args__ = (
        UniqueConstraint(
            "call_session_id", "ref", name="uq_ride_place_options_call_session_id_ref"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE")
    )
    # 1, 2, 3... in the order offered during the call; later searches go on counting.
    ref: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    # Street address when known, else "".
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    source: Mapped[PlaceSource] = mapped_column(_str_enum(PlaceSource, "source"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RideQuote(Base):
    """A price the agent read out during a call, bookable until `expires_at`."""

    __tablename__ = "ride_quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), index=True
    )
    pickup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ride_place_options.id", ondelete="CASCADE")
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ride_place_options.id", ondelete="CASCADE")
    )
    ride_type: Mapped[RideType] = mapped_column(_str_enum(RideType, "ride_type"))
    provider_quote_id: Mapped[str] = mapped_column(Text, unique=True)
    price_vnd: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[int] = mapped_column(Integer)
    # The trip itself, in seconds.
    duration_s: Mapped[int] = mapped_column(Integer)
    # Until a driver would reach the pickup, when quoted.
    pickup_eta_s: Mapped[int] = mapped_column(Integer)
    # Priced higher than usual by the provider.
    surge: Mapped[bool] = mapped_column(Boolean)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set by the service from its own clock: book_ride measures the quote's age with it.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    pickup: Mapped[RidePlaceOption] = relationship(
        foreign_keys=[pickup_id], lazy="joined", innerjoin=True
    )
    destination: Mapped[RidePlaceOption] = relationship(
        foreign_keys=[destination_id], lazy="joined", innerjoin=True
    )


class RideBooking(TimestampMixin, Base):
    """A ride booked for an elder (ACTIVE only), one per quote.

    Its status is the provider's, as last seen. The places are the quote's options.
    """

    __tablename__ = "ride_bookings"
    __table_args__ = (Index("ix_ride_bookings_elder_id_created_at", "elder_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("elders.id", ondelete="CASCADE"))
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE")
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ride_quotes.id", ondelete="CASCADE"), unique=True
    )
    provider_booking_id: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[RideStatus] = mapped_column(_str_enum(RideStatus, "status"))
    # Known once a driver accepted.
    driver_name: Mapped[str | None] = mapped_column(Text)
    driver_vehicle: Mapped[str | None] = mapped_column(Text)
    driver_plate: Mapped[str | None] = mapped_column(Text)
    # Set once cancelled.
    cancel_reason: Mapped[CancelReason | None] = mapped_column(
        _str_enum(CancelReason, "cancel_reason")
    )
    # When the status was last read from the provider (`app/services/ride/sync.py`).
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    quote: Mapped[RideQuote] = relationship(lazy="joined", innerjoin=True)

    @property
    def finished(self) -> bool:
        return self.status in FINISHED
