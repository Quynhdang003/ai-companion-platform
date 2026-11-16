"""`set_ride_sharing`: what the elder lets their family hear about their rides.

Asked once, right after the first booking; changed or withdrawn by voice in any call. The
ride alert job reads it when it sends (`app/services/notification/ride_alerts.py`).
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, RideShareScope


async def set_scope(db: AsyncSession, elder: Elder, scope: RideShareScope, now: datetime) -> None:
    """Store the elder's choice and when they made it (not committed)."""
    elder.ride_share_scope = scope
    elder.ride_share_decided_at = now
    await db.flush()
