"""Background job: tell the family on Telegram about high-risk scam events (NOTI-02).

The scam check marks an event `alert_status = pending` the first time it becomes high
(`app/services/scam/events.py`). This job sends the alert to every family member linked to
the elder who connected Telegram (one message per chat).

Each member gets an alert at most once: as soon as one send succeeds the event is `sent`,
and a member whose send failed then isn't retried (no duplicates for the others). Only when
every send fails is the event retried, `RETRY_DELAY` apart, up to `MAX_ATTEMPTS`, then
`failed`. Nobody to alert, or an event older than `MAX_AGE`: `skipped` (a late alert would
mislead). Logs carry event ids and counts only, never chat ids or names.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory, SessionLocal
from app.models import AlertStatus, Elder, ElderStatus, ScamEvent
from app.services.notification.channel import NotificationChannel
from app.services.notification.family import send_to_family
from app.services.notification.messages import scam_alert

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_DELAY = timedelta(seconds=30)
MAX_AGE = timedelta(hours=1)
BATCH_SIZE = 10


async def process_next(db: AsyncSession, channel: NotificationChannel) -> bool:
    """Alert for the oldest pending event that is due; False when none is left."""
    event = await db.scalar(
        select(ScamEvent)
        .where(
            ScamEvent.alert_status == AlertStatus.PENDING,
            or_(
                ScamEvent.alert_attempts == 0,
                ScamEvent.updated_at < func.now() - RETRY_DELAY,
            ),
        )
        .order_by(ScamEvent.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return False

    elder = await db.get(Elder, event.elder_id)
    if elder is None or elder.status is not ElderStatus.ACTIVE:
        return await _finish(db, event, AlertStatus.SKIPPED, "elder not active")
    if event.created_at < datetime.now(UTC) - MAX_AGE:
        return await _finish(db, event, AlertStatus.SKIPPED, "too old")
    text = scam_alert(elder.full_name, event.scam_type, event.risk_level, event.created_at)
    delivery = await send_to_family(db, channel, elder.id, text, label=f"scam alert {event.id}")
    if not delivery.chats:
        return await _finish(db, event, AlertStatus.SKIPPED, "no family member on Telegram")
    if delivery.sent:
        event.alerted_at = datetime.now(UTC)
        return await _finish(
            db, event, AlertStatus.SENT, f"sent to {delivery.sent} of {delivery.chats}"
        )
    if not delivery.failed:
        return await _finish(db, event, AlertStatus.SKIPPED, "every chat unreachable")
    event.alert_attempts += 1
    if event.alert_attempts >= MAX_ATTEMPTS:
        return await _finish(db, event, AlertStatus.FAILED, f"{event.alert_attempts} attempts")
    await db.commit()
    return True


async def _finish(db: AsyncSession, event: ScamEvent, status: AlertStatus, why: str) -> bool:
    event.alert_status = status
    await db.commit()
    logger.info("scam alert %s: %s (%s)", event.id, status.value, why)
    return True


async def run_alert_job(
    channel: NotificationChannel,
    session_factory: SessionFactory = SessionLocal,
    batch_size: int = BATCH_SIZE,
) -> int:
    """One scheduler run: up to `batch_size` events. Returns how many were handled."""
    handled = 0
    async with session_factory() as db:
        while handled < batch_size and await process_next(db, channel):
            handled += 1
    return handled
