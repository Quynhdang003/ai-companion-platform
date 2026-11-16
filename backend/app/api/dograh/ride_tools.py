"""Dograh tools for booking a ride (flow C), for ACTIVE elders only.

The agent names places by the option numbers `search_location` gave it, and books by ride
type: coordinates, prices and ids never come from the LLM. `book_ride` refuses a quote too
new to have been read out and agreed to (architecture invariant 5).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dograh.session import resolve_call
from app.core.config import get_settings
from app.core.db import DbSession
from app.core.dograh_auth import require_dograh_key
from app.core.errors import AppError
from app.models import CallSession, Elder, ElderStatus
from app.schemas.ride import (
    BookRideOut,
    BookRideRequest,
    PlaceOptionOut,
    RideQuoteOut,
    RideQuoteRequest,
    SearchLocationOut,
    SearchLocationRequest,
)
from app.services.ride import booking, messages, places
from app.services.ride.booking import (
    BookStatus,
    ConfirmationRequiredError,
    QuoteStatus,
    UnknownPlaceError,
)
from app.services.ride.places import SearchStatus
from app.services.ride.provider import RideProvider
from app.services.ride.simulator import get_ride_provider

router = APIRouter(prefix="/tools", tags=["dograh"], dependencies=[Depends(require_dograh_key)])

Provider = Annotated[RideProvider, Depends(get_ride_provider)]


async def _active_call(db: DbSession, token: str) -> CallSession:
    """The call, if its caller is an ACTIVE elder: rides need consent and an identity."""
    call = await resolve_call(db, token)
    elder = None if call.elder_id is None else await db.get(Elder, call.elder_id)
    if elder is None or elder.status is not ElderStatus.ACTIVE:
        raise AppError(403, "not_active", messages.NOT_ACTIVE)
    return call


def _minutes(seconds: int | None) -> int | None:
    return None if seconds is None else messages.whole_minutes(seconds)


@router.post("/search-location", response_model=SearchLocationOut)
async def search_location(
    body: SearchLocationRequest, db: DbSession, provider: Provider
) -> SearchLocationOut:
    """Up to 3 places for the caller's words, numbered for get_ride_quote."""
    call = await _active_call(db, body.session_token)
    result = await places.search(db, provider, call, body.query)
    await db.commit()
    if result.status is SearchStatus.FOUND:
        message = messages.places_found(result.options)
    elif result.status is SearchStatus.NOT_FOUND:
        message = messages.PLACE_NOT_FOUND
    else:
        message = messages.PLACES_UNAVAILABLE
    return SearchLocationOut(
        status=result.status,
        message=message,
        options=[
            PlaceOptionOut(ref=option.ref, name=option.name, address=option.address)
            for option in result.options
        ],
    )


@router.post("/get-ride-quote", response_model=RideQuoteOut)
async def get_ride_quote(body: RideQuoteRequest, db: DbSession, provider: Provider) -> RideQuoteOut:
    """Price and wait for a trip between two places of this call."""
    call = await _active_call(db, body.session_token)
    try:
        result = await booking.quote_ride(
            db,
            provider,
            call,
            pickup_ref=body.pickup_ref,
            destination_ref=body.destination_ref,
            ride_type=body.ride_type,
            now=datetime.now(UTC),
        )
    except UnknownPlaceError as exc:
        raise AppError(404, "unknown_place", messages.UNKNOWN_PLACE) from exc
    await db.commit()

    quote = result.quote
    if quote is None:
        message = {
            QuoteStatus.NO_DRIVER: messages.no_driver(body.ride_type),
            QuoteStatus.OUT_OF_AREA: messages.OUT_OF_AREA,
            QuoteStatus.TOO_SHORT: messages.TOO_SHORT,
            QuoteStatus.UNAVAILABLE: messages.QUOTE_UNAVAILABLE,
        }[result.status]
        return RideQuoteOut(status=result.status, message=message, ride_type=body.ride_type)
    return RideQuoteOut(
        status=result.status,
        message=messages.quoted(
            body.ride_type,
            result.pickup,
            result.destination,
            price_vnd=quote.price_vnd,
            trip_s=quote.duration_s,
            pickup_eta_s=quote.pickup_eta_s,
            surge=quote.surge,
        ),
        ride_type=body.ride_type,
        price_vnd=quote.price_vnd,
        pickup_minutes=_minutes(quote.pickup_eta_s),
        trip_minutes=_minutes(quote.duration_s),
        surge=quote.surge,
    )


@router.post("/book-ride", response_model=BookRideOut)
async def book_ride(body: BookRideRequest, db: DbSession, provider: Provider) -> BookRideOut:
    """Call only after the caller heard the price and clearly agreed to book."""
    call = await _active_call(db, body.session_token)
    settings = get_settings()
    try:
        result = await booking.book_ride(
            db,
            provider,
            call,
            ride_type=body.ride_type,
            now=datetime.now(UTC),
            confirm_after=timedelta(seconds=settings.ride_confirm_min_seconds),
        )
    except ConfirmationRequiredError as exc:
        raise AppError(409, "confirmation_required", messages.CONFIRMATION_REQUIRED) from exc
    await db.commit()

    ride = result.booking
    if result.status is BookStatus.BOOKED and ride is not None:
        message = messages.booked(body.ride_type, ride.quote.pickup, result.pickup_eta_s)
    else:
        message = {
            BookStatus.NO_QUOTE: messages.NO_QUOTE,
            BookStatus.QUOTE_EXPIRED: messages.QUOTE_EXPIRED,
            BookStatus.NO_DRIVER: messages.no_driver(body.ride_type),
            BookStatus.UNAVAILABLE: messages.BOOK_UNAVAILABLE,
        }[result.status]
    return BookRideOut(
        status=result.status,
        message=message,
        ride_type=body.ride_type,
        pickup_minutes=_minutes(result.pickup_eta_s),
    )
