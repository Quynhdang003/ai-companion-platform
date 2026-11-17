"""Send one message to the Telegram chat of every family member linked to an elder.

Shared by the alert jobs (`scam_alerts.py`, `ride_alerts.py`). A chat that blocked the bot
is disconnected; logs carry counts only, never chat ids or names.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ElderFamily, TelegramLink
from app.services.notification import telegram_links
from app.services.notification.channel import (
    NotificationChannel,
    NotificationError,
    RecipientUnreachableError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Delivery:
    chats: int  # connected chats of the elder's family
    sent: int
    failed: int  # sends that may go through later (unreachable chats don't count)


async def family_chats(db: AsyncSession, elder_id: uuid.UUID) -> list[int]:
    """Telegram chats of the elder's family members (owner and viewers), each once."""
    rows = await db.scalars(
        select(TelegramLink.chat_id)
        .join(ElderFamily, ElderFamily.user_id == TelegramLink.user_id)
        .where(ElderFamily.elder_id == elder_id, TelegramLink.chat_id.is_not(None))
        .distinct()
        .order_by(TelegramLink.chat_id)
    )
    return [chat_id for chat_id in rows if chat_id is not None]


async def send_to_family(
    db: AsyncSession,
    channel: NotificationChannel,
    elder_id: uuid.UUID,
    text: str,
    *,
    label: str,
) -> Delivery:
    """`label` names what is sent in the logs (e.g. "scam alert <id>")."""
    chats = await family_chats(db, elder_id)
    sent = failed = 0
    for chat_id in chats:
        try:
            await channel.send(str(chat_id), text)
            sent += 1
        except RecipientUnreachableError:
            await telegram_links.unlink_chat(db, chat_id)
        except NotificationError as exc:
            failed += 1
            logger.warning("%s: a send failed: %s", label, exc)
    return Delivery(chats=len(chats), sent=sent, failed=failed)
