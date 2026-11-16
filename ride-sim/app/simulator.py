"""Quotes and bookings: what the routes call."""

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.dispatch import Driver, nearest_driver, pickup_duration_s, seed_drivers
from app.errors import AppError
from app.geo import SERVICE_AREA, Point
from app.models import Booking, CancelReason, Quote, RideStatus, RideType
from app.pricing import is_peak, price_vnd
from app.routing import Router
from app.state import ASSIGN_DELAY_S, CANCELLABLE, Timeline, plan_timeline, status_at

# Shorter than this isn't a ride (also catches the same place given twice).
MIN_TRIP_DISTANCE_M = 200

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class BookingView:
    """A booking as it is right now."""

    booking: Booking
    status: RideStatus
    # Known once a driver accepted; a ride cancelled before that never had one.
    driver: Driver | None
    # Simulated seconds left, while they still mean something.
    pickup_eta_s: int | None
    dropoff_eta_s: int | None


class Simulator:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        router: Router,
        clock: Clock = utc_now,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._router = router
        self._clock = clock
        self._drivers = seed_drivers(settings.seed, settings.driver_count)
        self._drivers_by_id = {driver.id: driver for driver in self._drivers}
        # One booking at a time, so two requests can't be given the same free driver.
        self._booking_lock = asyncio.Lock()

    async def create_quote(self, ride_type: RideType, pickup: Point, destination: Point) -> Quote:
        if not (SERVICE_AREA.contains(pickup) and SERVICE_AREA.contains(destination)):
            raise AppError(422, "out_of_service_area", "Pickup and destination must be in Hanoi")
        route = await self._router.route(pickup, destination)
        if route.distance_m < MIN_TRIP_DISTANCE_M:
            raise AppError(422, "trip_too_short", "Pickup and destination are the same place")

        now = self._clock()
        peak = is_peak(now)
        async with self._sessions() as db:
            driver = await self._free_driver(db, ride_type, pickup, now)
            quote = Quote(
                ride_type=ride_type,
                pickup_lat=pickup.lat,
                pickup_lng=pickup.lng,
                destination_lat=destination.lat,
                destination_lng=destination.lng,
                distance_m=route.distance_m,
                duration_s=route.duration_s,
                price_vnd=price_vnd(ride_type, route.distance_m, route.duration_s, peak=peak),
                peak=peak,
                estimated=route.estimated,
                pickup_eta_s=(
                    None if driver is None else ASSIGN_DELAY_S + pickup_duration_s(driver, pickup)
                ),
                created_at=now,
                expires_at=now + timedelta(seconds=self._settings.quote_ttl_seconds),
            )
            db.add(quote)
            await db.commit()
        return quote

    async def create_booking(self, quote_id: str) -> tuple[BookingView, bool]:
        """Book a quote. False when it was booked before: that booking is returned as is,
        so a caller that lost the first answer can simply ask again."""
        async with self._booking_lock, self._sessions() as db:
            quote = await db.get(Quote, quote_id)
            if quote is None:
                raise AppError(404, "quote_not_found", "Quote not found")
            existing = await db.scalar(select(Booking).where(Booking.quote_id == quote_id))
            if existing is not None:
                return self._view(existing), False

            now = self._clock()
            if now >= quote.expires_at:
                raise AppError(409, "quote_expired", "Quote has expired; ask for a new one")
            driver = await self._free_driver(db, quote.ride_type, quote.pickup, now)
            if driver is None:
                raise AppError(409, "no_driver_available", "No driver is available nearby")

            timeline = plan_timeline(
                now,
                pickup_duration_s=pickup_duration_s(driver, quote.pickup),
                trip_duration_s=quote.duration_s,
                time_scale=self._settings.time_scale,
            )
            booking = Booking(
                quote=quote,
                driver_id=driver.id,
                time_scale=self._settings.time_scale,
                requested_at=timeline.requested_at,
                assigned_at=timeline.assigned_at,
                arriving_at=timeline.arriving_at,
                pickup_at=timeline.pickup_at,
                dropoff_at=timeline.dropoff_at,
            )
            db.add(booking)
            await db.commit()
            return self._view(booking), True

    async def get_booking(self, booking_id: str) -> BookingView:
        async with self._sessions() as db:
            return self._view(await self._booking(db, booking_id))

    async def cancel_booking(self, booking_id: str) -> BookingView:
        """Cancel for the rider; cancelling a cancelled ride changes nothing."""
        async with self._sessions() as db:
            booking = await self._booking(db, booking_id)
            status = self._view(booking).status
            if status is RideStatus.IN_PROGRESS:
                raise AppError(409, "ride_in_progress", "The passenger is already on board")
            if status is RideStatus.COMPLETED:
                raise AppError(409, "ride_completed", "The ride is already completed")
            if status in CANCELLABLE:
                booking.cancelled_at = self._clock()
                booking.cancel_reason = CancelReason.RIDER
                await db.commit()
            return self._view(booking)

    async def _booking(self, db: AsyncSession, booking_id: str) -> Booking:
        booking = await db.get(Booking, booking_id)
        if booking is None:
            raise AppError(404, "booking_not_found", "Booking not found")
        return booking

    async def _free_driver(
        self, db: AsyncSession, ride_type: RideType, pickup: Point, now: datetime
    ) -> Driver | None:
        # Drivers are busy from the booking until its drop-off or cancellation.
        busy = await db.scalars(
            select(Booking.driver_id).where(
                Booking.dropoff_at > now,
                or_(Booking.cancelled_at.is_(None), Booking.cancelled_at > now),
            )
        )
        return nearest_driver(self._drivers, ride_type, pickup, busy=set(busy))

    def _view(self, booking: Booking) -> BookingView:
        now = self._clock()
        timeline = Timeline(
            requested_at=booking.requested_at,
            assigned_at=booking.assigned_at,
            arriving_at=booking.arriving_at,
            pickup_at=booking.pickup_at,
            dropoff_at=booking.dropoff_at,
        )
        status = status_at(now, timeline, booking.cancelled_at)
        ended_or_now = now if booking.cancelled_at is None else min(now, booking.cancelled_at)

        def left(until: datetime) -> int:
            simulated = (until - now).total_seconds() * booking.time_scale
            return max(0, math.ceil(round(simulated, 3)))

        waiting = status in CANCELLABLE
        return BookingView(
            booking=booking,
            status=status,
            driver=(
                self._drivers_by_id.get(booking.driver_id)
                if ended_or_now >= booking.assigned_at
                else None
            ),
            pickup_eta_s=left(booking.pickup_at) if waiting else None,
            dropoff_eta_s=(
                left(booking.dropoff_at) if waiting or status is RideStatus.IN_PROGRESS else None
            ),
        )
