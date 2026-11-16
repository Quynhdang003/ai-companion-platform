from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import FamilyUser
from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import AppError
from app.models import TelegramLink
from app.schemas.telegram import TelegramLinkOut, TelegramStatusOut
from app.services.notification import telegram_links

router = APIRouter(prefix="/api/telegram", tags=["web"])


def get_bot_username() -> str | None:
    """The bot's username when Telegram is set up on this server, else None."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return None
    return settings.telegram_bot_username.lstrip("@") or None


BotUsername = Annotated[str | None, Depends(get_bot_username)]


@router.get("", response_model=TelegramStatusOut)
async def read_status(user: FamilyUser, db: DbSession, bot: BotUsername) -> TelegramStatusOut:
    return _status(bot, await telegram_links.get_link(db, user))


@router.post("/link", response_model=TelegramLinkOut)
async def create_link(user: FamilyUser, db: DbSession, bot: BotUsername) -> TelegramLinkOut:
    if bot is None:
        raise AppError(500, "telegram_not_configured", "Telegram alerts are not configured")
    ttl = timedelta(minutes=get_settings().telegram_link_ttl_minutes)
    link = await telegram_links.create_link(db, user, bot_username=bot, ttl=ttl)
    await db.commit()
    return TelegramLinkOut(url=link.url, expires_at=link.expires_at)


@router.delete("", response_model=TelegramStatusOut)
async def disconnect(user: FamilyUser, db: DbSession, bot: BotUsername) -> TelegramStatusOut:
    await telegram_links.unlink(db, user)
    await db.commit()
    return _status(bot, None)


def _status(bot: str | None, link: TelegramLink | None) -> TelegramStatusOut:
    linked = link if link is not None and link.chat_id is not None else None
    return TelegramStatusOut(
        enabled=bot is not None,
        connected=linked is not None,
        linked_at=linked.linked_at if linked else None,
    )
