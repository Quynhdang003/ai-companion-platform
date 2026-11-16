"""`get_ride_status` and `cancel_ride`: the elder's current ride, as the provider sees it now."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallSession, CancelReason, RideBooking, RideStatus
from app.services.ride import provider as codes
from app.services.ride.provider import (
    ProviderBooking,
    RideProvider,
    RideProviderUnavailableError,
    RideRequestRefusedError,
)

logger = logging.getLogger(__name__)

# A finished ride is still "the current ride" for this long: asked an hour after arriving,
# the agent says it arrived rather than "no ride".
FINISHED_RIDE_KEPT = timedelta(hours=6)


class StatusOutcome(StrEnum):
    FOUND = "found"
    NO_RIDE = "no_ride"
    UNAVAILABLE = "unavailable"  # the provider didn't answer: the stored status is shown


class CancelOutcome(StrEnum):
    CANCELLED = "cancelled"
    ALREADY_CANCELLED = "already_cancelled"  # by the elder before, the driver, or lost
    IN_PROGRESS = "in_progress"  # passenger on board: too late
    COMPLETED = "completed"
    NO_RIDE = "no_ride"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RideView:
    outcome: StatusOutcome
    booking: RideBooking | None = None
    # Live, when the provider just answered.
    pickup_eta_s: int | None = None
    dropoff_eta_s: int | None = None


@dataclass(frozen=True)
class CancelResult:
    outcome: CancelOutcome
    booking: RideBooking | None = None


def apply(booking: RideBooking, ride: ProviderBooking, now: datetime) -> bool:
    """Copy the provider's view of the ride onto the stored booking; True if the status moved."""
    moved = booking.status is not ride.status
    booking.status = ride.status
    if ride.driver is not None:
        booking.driver_name = ride.driver.name
        booking.driver_vehicle = ride.driver.vehicle
        booking.driver_plate = ride.driver.plate
    if ride.status is RideStatus.CANCELLED:
        reason = ride.cancel_reason
        booking.cancel_reason = (
            CancelReason(reason) if reason in (CancelReason.RIDER, CancelReason.DRIVER) else None
        )
    booking.synced_at = now
    return moved


def mark_lost(booking: RideBooking, now: datetime) -> None:
    """The provider no longer knows the booking (e.g. the simulator's state was deleted)."""
    logger.warning("Ride booking %s is unknown to the provider: marked lost", booking.id)
    booking.status = RideStatus.CANCELLED
    booking.cancel_reason = CancelReason.LOST
    booking.synced_at = now


async def current_ride(db: AsyncSession, elder_id: uuid.UUID, now: datetime) -> RideBooking | None:
    """The elder's latest ride, locked; None if none, or it finished long ago."""
    booking = await db.scalar(
        select(RideBooking)
        .where(RideBooking.elder_id == elder_id)
        .order_by(RideBooking.created_at.desc())
        .limit(1)
        .with_for_update(of=RideBooking)
    )
    if booking is None or (booking.finished and booking.created_at < now - FINISHED_RIDE_KEPT):
        return None
    return booking


async def ride_status(
    db: AsyncSession, provider: RideProvider, call: CallSession, *, now: datetime
) -> RideView:
    """The current ride, refreshed from the provider while it isn't finished (not committed)."""
    assert call.elder_id is not None
    booking = await current_ride(db, call.elder_id, now)
    if booking is None:
        return RideView(StatusOutcome.NO_RIDE)
    if booking.finished:
        return RideView(StatusOutcome.FOUND, booking)
    try:
        ride = await provider.get_booking(booking.provider_booking_id)
    except RideRequestRefusedError as exc:
        if exc.code != codes.BOOKING_NOT_FOUND:
            logger.warning("Ride status refused with %s", exc.code)
            return RideView(StatusOutcome.UNAVAILABLE, booking)
        mark_lost(booking, now)
        await db.flush()
        return RideView(StatusOutcome.FOUND, booking)
    except RideProviderUnavailableError as exc:
        logger.warning("Ride status failed: %s", exc)
        return RideView(StatusOutcome.UNAVAILABLE, booking)
    apply(booking, ride, now)
    await db.flush()
    return RideView(StatusOutcome.FOUND, booking, ride.pickup_eta_s, ride.dropoff_eta_s)


async def cancel_ride(
    db: AsyncSession, provider: RideProvider, call: CallSession, *, now: datetime
) -> CancelResult:
    """Cancel the current ride for the elder (not committed)."""
    assert call.elder_id is not None
    booking = await current_ride(db, call.elder_id, now)
    if booking is None:
        return CancelResult(CancelOutcome.NO_RIDE)
    if booking.status is RideStatus.CANCELLED:
        return CancelResult(CancelOutcome.ALREADY_CANCELLED, booking)
    if booking.status is RideStatus.COMPLETED:
        return CancelResult(CancelOutcome.COMPLETED, booking)
    try:
        ride = await provider.cancel(booking.provider_booking_id)
    except RideRequestRefusedError as exc:
        refused = {
            codes.RIDE_IN_PROGRESS: CancelOutcome.IN_PROGRESS,
            codes.RIDE_COMPLETED: CancelOutcome.COMPLETED,
        }.get(exc.code)
        if refused is not None:
            return CancelResult(refused, booking)
        if exc.code == codes.BOOKING_NOT_FOUND:
            mark_lost(booking, now)
            await db.flush()
            return CancelResult(CancelOutcome.ALREADY_CANCELLED, booking)
        logger.warning("Ride cancel refused with %s", exc.code)
        return CancelResult(CancelOutcome.UNAVAILABLE, booking)
    except RideProviderUnavailableError as exc:
        logger.warning("Ride cancel failed: %s", exc)
        return CancelResult(CancelOutcome.UNAVAILABLE, booking)
    apply(booking, ride, now)
    await db.flush()
    if ride.status is RideStatus.CANCELLED and booking.cancel_reason is CancelReason.RIDER:
        return CancelResult(CancelOutcome.CANCELLED, booking)
    # The driver had cancelled first: cancelling again changed nothing.
    return CancelResult(CancelOutcome.ALREADY_CANCELLED, booking)
