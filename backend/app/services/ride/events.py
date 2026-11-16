"""Queue ride updates for the family (`ride_notifications`), one per ride and event.

Queued whatever the elder chose to share: the alert job checks the choice when it sends.
"""

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CancelReason, RideBooking, RideEvent, RideNotification, RideStatus

# Statuses the family hears about once a ride reaches them; the driver's moves don't count.
_STATUS_EVENTS = {
    RideStatus.IN_PROGRESS: RideEvent.ON_THE_WAY,
    RideStatus.COMPLETED: RideEvent.ARRIVED,
    RideStatus.CANCELLED: RideEvent.CANCELLED,
}


async def queue(db: AsyncSession, booking: RideBooking, event: RideEvent, now: datetime) -> None:
    """Queue the update (not committed); an event already queued for the ride is kept."""
    await db.execute(
        insert(RideNotification)
        .values(booking_id=booking.id, event=event, created_at=now, updated_at=now)
        .on_conflict_do_nothing(constraint="uq_ride_notifications_booking_id_event")
    )


async def queue_status(db: AsyncSession, booking: RideBooking, now: datetime) -> None:
    """Queue the update for the ride's new status, if the family hears about it.

    A lost ride (the provider forgot it) isn't news to anyone: nothing is queued.
    """
    event = _STATUS_EVENTS.get(booking.status)
    if event is not None and booking.cancel_reason is not CancelReason.LOST:
        await queue(db, booking, event, now)
