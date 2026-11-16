"""Background job: keep open rides in step with the provider (RIDE-02).

Each run reads every open ride (before COMPLETED or CANCELLED) once, the longest unread
first, and copies its status, driver and cancel reason. The tools refresh a ride as well
when the elder asks about it. A provider without an answer stops the run: the next one goes
on. A ride the provider no longer knows is marked cancelled, `lost`.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory, SessionLocal
from app.models import RideBooking, RideStatus
from app.services.ride import provider as codes
from app.services.ride.provider import (
    RideProvider,
    RideProviderUnavailableError,
    RideRequestRefusedError,
)
from app.services.ride.rides import apply, mark_lost
from app.services.ride.simulator import get_ride_provider

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
OPEN = (
    RideStatus.REQUESTED,
    RideStatus.DRIVER_ASSIGNED,
    RideStatus.ARRIVING,
    RideStatus.IN_PROGRESS,
)


async def sync_next(db: AsyncSession, provider: RideProvider, *, started: datetime) -> bool:
    """Read one open ride not read since `started`; False when none is left.

    The ride is claimed (its `synced_at` set) and released before the provider is asked:
    the elder's own status or cancel request never waits behind a slow provider here. The
    answer is written only if no tool read the ride in the meantime (theirs is as new).
    """
    booking = await db.scalar(
        select(RideBooking)
        .where(
            RideBooking.status.in_(OPEN),
            or_(RideBooking.synced_at.is_(None), RideBooking.synced_at < started),
        )
        .order_by(RideBooking.synced_at.asc().nulls_first())
        .limit(1)
        .with_for_update(of=RideBooking, skip_locked=True)
    )
    if booking is None:
        return False
    booking_id, provider_booking_id = booking.id, booking.provider_booking_id
    claimed_at = booking.synced_at = datetime.now(UTC)
    await db.commit()

    # Unavailable propagates and stops the run; the claim stands, the next run retries.
    try:
        ride = await provider.get_booking(provider_booking_id)
    except RideRequestRefusedError as exc:
        if exc.code != codes.BOOKING_NOT_FOUND:
            logger.warning("Ride sync of %s refused with %s", booking_id, exc.code)
            return True
        ride = None

    booking = await db.scalar(
        select(RideBooking)
        .where(RideBooking.id == booking_id)
        .with_for_update(of=RideBooking)
        .execution_options(populate_existing=True)
    )
    if booking is not None and booking.synced_at == claimed_at:
        now = datetime.now(UTC)
        if ride is None:
            mark_lost(booking, now)
        else:
            apply(booking, ride, now)
    await db.commit()
    return True


async def run_ride_sync_job(
    session_factory: SessionFactory = SessionLocal,
    provider: RideProvider | None = None,
    batch_size: int = BATCH_SIZE,
) -> int:
    """One scheduler run: up to `batch_size` rides. Returns how many were read."""
    provider = provider or get_ride_provider()
    started = datetime.now(UTC)
    synced = 0
    async with session_factory() as db:
        try:
            while synced < batch_size and await sync_next(db, provider, started=started):
                synced += 1
        except RideProviderUnavailableError as exc:
            # The ride being read is unchanged; closing the session releases its lock.
            logger.warning("Ride sync paused until its next run: %s", exc)
    return synced
