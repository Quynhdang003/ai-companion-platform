"""`get_ride_quote` and `book_ride`: price a trip between two of the call's places, then
book that price once the caller agreed to it.

The agent only ever names places by their option number and the ride type: coordinates,
prices and provider ids stay here.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CallSession,
    RideBooking,
    RideEvent,
    RidePlaceOption,
    RideQuote,
    RideType,
)
from app.services.ride import events
from app.services.ride import provider as codes
from app.services.ride.provider import (
    GeoPoint,
    RideProvider,
    RideProviderUnavailableError,
    RideRequestRefusedError,
)

logger = logging.getLogger(__name__)


class UnknownPlaceError(Exception):
    """No option with that number in this call."""


class ConfirmationRequiredError(Exception):
    """The quote is too new to have been read out and agreed to."""


class QuoteStatus(StrEnum):
    QUOTED = "quoted"
    NO_DRIVER = "no_driver"  # no driver of that type near the pickup
    OUT_OF_AREA = "out_of_area"
    TOO_SHORT = "too_short"
    UNAVAILABLE = "unavailable"  # the provider didn't answer


class BookStatus(StrEnum):
    BOOKED = "booked"
    NO_QUOTE = "no_quote"  # nothing quoted for that ride type in this call
    QUOTE_EXPIRED = "quote_expired"
    NO_DRIVER = "no_driver"
    UNAVAILABLE = "unavailable"  # the provider didn't answer: asking again is safe


@dataclass(frozen=True)
class QuoteResult:
    status: QuoteStatus
    pickup: RidePlaceOption
    destination: RidePlaceOption
    # Set when quoted.
    quote: RideQuote | None = None


@dataclass(frozen=True)
class BookResult:
    status: BookStatus
    # Set when booked.
    booking: RideBooking | None = None
    # Live, from the provider, when it just booked.
    pickup_eta_s: int | None = None
    # Booked by this request (not a quote booked before).
    new: bool = False


_QUOTE_REFUSALS = {
    codes.OUT_OF_SERVICE_AREA: QuoteStatus.OUT_OF_AREA,
    codes.TRIP_TOO_SHORT: QuoteStatus.TOO_SHORT,
}
_BOOK_REFUSALS = {
    codes.QUOTE_EXPIRED: BookStatus.QUOTE_EXPIRED,
    codes.QUOTE_NOT_FOUND: BookStatus.QUOTE_EXPIRED,
    codes.NO_DRIVER_AVAILABLE: BookStatus.NO_DRIVER,
}


async def quote_ride(
    db: AsyncSession,
    provider: RideProvider,
    call: CallSession,
    *,
    pickup_ref: int,
    destination_ref: int,
    ride_type: RideType,
    now: datetime,
) -> QuoteResult:
    """Price the trip; a quote with a driver nearby is stored (not committed)."""
    pickup = await _option(db, call, pickup_ref)
    destination = await _option(db, call, destination_ref)
    try:
        offer = await provider.quote(
            ride_type, GeoPoint(pickup.lat, pickup.lng), GeoPoint(destination.lat, destination.lng)
        )
    except RideRequestRefusedError as exc:
        status = _QUOTE_REFUSALS.get(exc.code, QuoteStatus.UNAVAILABLE)
        if status is QuoteStatus.UNAVAILABLE:
            logger.warning("Ride quote refused with %s", exc.code)
        return QuoteResult(status, pickup, destination)
    except RideProviderUnavailableError as exc:
        logger.warning("Ride quote failed: %s", exc)
        return QuoteResult(QuoteStatus.UNAVAILABLE, pickup, destination)
    if offer.pickup_eta_s is None:
        return QuoteResult(QuoteStatus.NO_DRIVER, pickup, destination)

    quote = RideQuote(
        call_session_id=call.id,
        pickup_id=pickup.id,
        destination_id=destination.id,
        ride_type=ride_type,
        provider_quote_id=offer.id,
        price_vnd=offer.price_vnd,
        distance_m=offer.distance_m,
        duration_s=offer.duration_s,
        pickup_eta_s=offer.pickup_eta_s,
        surge=offer.surge,
        expires_at=offer.expires_at,
        created_at=now,
    )
    db.add(quote)
    await db.flush()
    return QuoteResult(QuoteStatus.QUOTED, pickup, destination, quote)


async def book_ride(
    db: AsyncSession,
    provider: RideProvider,
    call: CallSession,
    *,
    ride_type: RideType,
    now: datetime,
    confirm_after: timedelta,
) -> BookResult:
    """Book the call's latest quote of `ride_type` (not committed).

    Raises `ConfirmationRequiredError` for a quote younger than `confirm_after`: its price
    can't have been read out and agreed to yet. A quote already booked returns its booking
    again; one the provider may have booked before failing is safely asked again.
    """
    assert call.elder_id is not None
    # Locked: two bookings at once of the same quote would both reach the provider.
    quote = await db.scalar(
        select(RideQuote)
        .where(RideQuote.call_session_id == call.id, RideQuote.ride_type == ride_type)
        .order_by(RideQuote.created_at.desc())
        .limit(1)
        .with_for_update(of=RideQuote)
    )
    if quote is None:
        return BookResult(BookStatus.NO_QUOTE)
    existing = await db.scalar(select(RideBooking).where(RideBooking.quote_id == quote.id))
    if existing is not None:
        return BookResult(BookStatus.BOOKED, existing)
    if now - quote.created_at < confirm_after:
        raise ConfirmationRequiredError
    if now >= quote.expires_at:
        return BookResult(BookStatus.QUOTE_EXPIRED)

    try:
        ride = await provider.book(quote.provider_quote_id)
    except RideRequestRefusedError as exc:
        status = _BOOK_REFUSALS.get(exc.code, BookStatus.UNAVAILABLE)
        if status is BookStatus.UNAVAILABLE:
            logger.warning("Ride booking refused with %s", exc.code)
        return BookResult(status)
    except RideProviderUnavailableError as exc:
        logger.warning("Ride booking failed: %s", exc)
        return BookResult(BookStatus.UNAVAILABLE)

    driver = ride.driver
    booking = RideBooking(
        elder_id=call.elder_id,
        call_session_id=call.id,
        quote=quote,
        provider_booking_id=ride.id,
        status=ride.status,
        driver_name=driver.name if driver else None,
        driver_vehicle=driver.vehicle if driver else None,
        driver_plate=driver.plate if driver else None,
        # The service's clock, like the quote's: rides are ordered by it ("last ride").
        created_at=now,
    )
    db.add(booking)
    await db.flush()
    await events.queue(db, booking, RideEvent.BOOKED, now)
    return BookResult(BookStatus.BOOKED, booking, ride.pickup_eta_s, new=True)


async def _option(db: AsyncSession, call: CallSession, ref: int) -> RidePlaceOption:
    option = await db.scalar(
        select(RidePlaceOption).where(
            RidePlaceOption.call_session_id == call.id, RidePlaceOption.ref == ref
        )
    )
    if option is None:
        raise UnknownPlaceError
    return option
