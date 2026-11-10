"""Family members connect Telegram with a one-time link (`t.me/<bot>?start=<token>`).

Opening it makes Telegram send `/start <token>` to the bot from the member's chat; the
update poller (`telegram_updates.py`) then links that chat to the member. No public URL is
needed: the backend fetches the bot's messages itself.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramLink, User
from app.services.identity.call_sessions import hash_token


@dataclass(frozen=True)
class ConnectLink:
    url: str
    expires_at: datetime


async def create_link(
    db: AsyncSession, user: User, *, bot_username: str, ttl: timedelta
) -> ConnectLink:
    """A new one-time connect link for `user`; any earlier unused link stops working.

    A chat already linked stays linked until the new link is used (then it's replaced).
    """
    token = secrets.token_urlsafe(32)  # 43 characters: Telegram allows up to 64.
    expires_at = datetime.now(UTC) + ttl
    values = {"link_token_hash": hash_token(token), "link_token_expires_at": expires_at}
    await db.execute(
        insert(TelegramLink)
        .values(user_id=user.id, **values)
        .on_conflict_do_update(
            index_elements=[TelegramLink.user_id], set_={**values, "updated_at": func.now()}
        )
    )
    return ConnectLink(f"https://t.me/{bot_username}?start={token}", expires_at)


async def redeem(db: AsyncSession, token: str, chat_id: int) -> uuid.UUID | None:
    """Link `chat_id` to the owner of a live connect token; the token then stops working.

    Returns the linked user's id, or None for an unknown, used or expired token.
    """
    return await db.scalar(
        update(TelegramLink)
        .where(
            TelegramLink.link_token_hash == hash_token(token),
            TelegramLink.link_token_expires_at > datetime.now(UTC),
        )
        .values(
            chat_id=chat_id,
            linked_at=func.now(),
            link_token_hash=None,
            link_token_expires_at=None,
            updated_at=func.now(),
        )
        .returning(TelegramLink.user_id)
    )


async def get_link(db: AsyncSession, user: User) -> TelegramLink | None:
    return await db.scalar(select(TelegramLink).where(TelegramLink.user_id == user.id))


async def unlink(db: AsyncSession, user: User) -> None:
    """Stop sending to `user`'s chat and drop any unused connect link."""
    await db.execute(delete(TelegramLink).where(TelegramLink.user_id == user.id))


async def unlink_chat(db: AsyncSession, chat_id: int) -> None:
    """Forget a chat that can't get messages any more (e.g. it blocked the bot)."""
    await db.execute(delete(TelegramLink).where(TelegramLink.chat_id == chat_id))
