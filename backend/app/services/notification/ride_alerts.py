"""Background job: tell the family on Telegram about the elder's rides (RIDE-03).

Updates are queued for every ride whatever the elder chose (`app/services/ride/events.py`);
this job reads the elder's `ride_share_scope` when it sends, so a change, a withdrawal
included, applies at once, also to a ride in progress:

- not asked yet: the update waits for the elder's answer (asked right after booking), up to
  `MAX_AGE`, then is skipped;
- `none`: skipped; `status`: event, ride type and time; `details`: plus places and the car.

Sending follows the scam alerts (`scam_alerts.py`): each member at most once, all sends
failing are retried `RETRY_DELAY` apart, then `failed`. Logs carry ids and counts only.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory, SessionLocal
from app.models import (
    AlertStatus,
    Elder,
    ElderStatus,
    RideBooking,
    RideNotification,
    RideShareScope,
)
from app.services.notification.channel import NotificationChannel
from app.services.notification.family import send_to_family
from app.services.notification.messages import ride_update

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_DELAY = timedelta(seconds=30)
# Older updates are no news: "booked" an hour later would mislead.
MAX_AGE = timedelta(minutes=15)
BATCH_SIZE = 10


async def process_next(db: AsyncSession, channel: NotificationChannel) -> bool:
    """Send or settle the oldest due update; False when none is left."""
    now = datetime.now(UTC)
    note = await db.scalar(
        select(RideNotification)
        .join(RideBooking, RideBooking.id == RideNotification.booking_id)
        .join(Elder, Elder.id == RideBooking.elder_id)
        .where(
            RideNotification.status == AlertStatus.PENDING,
            or_(
                RideNotification.attempts == 0,
                RideNotification.updated_at < func.now() - RETRY_DELAY,
            ),
            # Not asked yet: wait for the elder's answer, until the update is too old.
            or_(Elder.ride_share_scope.is_not(None), RideNotification.created_at < now - MAX_AGE),
        )
        .order_by(RideNotification.created_at)
        .limit(1)
        .with_for_update(of=RideNotification, skip_locked=True)
    )
    if note is None:
        return False

    booking = await db.get(RideBooking, note.booking_id, populate_existing=True)
    assert booking is not None
    # Read now: the elder may have changed their mind since the update was queued.
    elder = await db.get(Elder, booking.elder_id, populate_existing=True)
    if elder is None or elder.status is not ElderStatus.ACTIVE:
        return await _finish(db, note, AlertStatus.SKIPPED, "elder not active")
    if note.created_at < now - MAX_AGE:
        return await _finish(db, note, AlertStatus.SKIPPED, "too old")
    scope = elder.ride_share_scope
    if scope is None or scope is RideShareScope.NONE:
        return await _finish(db, note, AlertStatus.SKIPPED, "not shared")

    text = ride_update(elder.full_name, note.event, note.created_at, booking, scope)
    delivery = await send_to_family(db, channel, elder.id, text, label=f"ride update {note.id}")
    if not delivery.chats:
        return await _finish(db, note, AlertStatus.SKIPPED, "no family member on Telegram")
    if delivery.sent:
        note.sent_at = datetime.now(UTC)
        return await _finish(
            db, note, AlertStatus.SENT, f"sent to {delivery.sent} of {delivery.chats}"
        )
    if not delivery.failed:
        return await _finish(db, note, AlertStatus.SKIPPED, "every chat unreachable")
    note.attempts += 1
    if note.attempts >= MAX_ATTEMPTS:
        return await _finish(db, note, AlertStatus.FAILED, f"{note.attempts} attempts")
    await db.commit()
    return True


async def _finish(db: AsyncSession, note: RideNotification, status: AlertStatus, why: str) -> bool:
    note.status = status
    await db.commit()
    logger.info("ride update %s (%s): %s (%s)", note.id, note.event.value, status.value, why)
    return True


async def run_ride_alert_job(
    channel: NotificationChannel,
    session_factory: SessionFactory = SessionLocal,
    batch_size: int = BATCH_SIZE,
) -> int:
    """One scheduler run: up to `batch_size` updates. Returns how many were handled."""
    handled = 0
    async with session_factory() as db:
        while handled < batch_size and await process_next(db, channel):
            handled += 1
    return handled
