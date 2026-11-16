"""Background job: read the bot's new messages and link chats that send `/start <token>`.

Polls `getUpdates` from the scheduler (`app/core/scheduler.py`), so the backend needs no
public URL. Only private chats count. Every message gets a short reply. Logs never carry
chat ids, tokens or message text.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory, SessionLocal
from app.services.notification import telegram_links
from app.services.notification.channel import NotificationChannel, NotificationError
from app.services.notification.telegram import TelegramApi, TelegramUpdate

logger = logging.getLogger(__name__)

LINKED = (
    "Đã kết nối Telegram với Touch the Light. Khi trợ lý thấy người thân của bạn có nguy cơ "
    "cao bị lừa đảo trong cuộc gọi, bạn sẽ nhận tin báo ở đây. Muốn ngừng nhận, bấm "
    "“Ngắt kết nối” trên trang tổng quan."
)
LINK_INVALID = (
    "Liên kết này không dùng được nữa: đã hết hạn hoặc đã được dùng. Bạn vào trang tổng "
    "quan Touch the Light, bấm “Kết nối Telegram” để lấy liên kết mới."
)
HELP = (
    "Đây là bot cảnh báo lừa đảo của Touch the Light. Để nhận cảnh báo về người thân, bạn "
    "vào trang tổng quan và bấm “Kết nối Telegram”."
)


async def handle_update(db: AsyncSession, bot: NotificationChannel, update: TelegramUpdate) -> None:
    message = update.message
    if message is None or message.chat.type != "private" or message.text is None:
        return
    command, _, argument = message.text.strip().partition(" ")
    token = argument.strip()
    if command.split("@")[0] != "/start" or not token:
        await _reply(bot, message.chat.id, HELP)
        return

    user_id = await telegram_links.redeem(db, token, message.chat.id)
    await db.commit()
    if user_id is None:
        await _reply(bot, message.chat.id, LINK_INVALID)
        return
    logger.info("telegram connected for user %s", user_id)
    await _reply(bot, message.chat.id, LINKED)


async def _reply(bot: NotificationChannel, chat_id: int, text: str) -> None:
    # A lost reply doesn't undo the link: the dashboard shows the status anyway.
    try:
        await bot.send(str(chat_id), text)
    except NotificationError as exc:
        logger.warning("telegram reply failed: %s", exc)


class TelegramUpdatePoller:
    """Keeps the `getUpdates` offset between runs (Telegram keeps it across restarts)."""

    def __init__(self, bot: TelegramApi, session_factory: SessionFactory = SessionLocal) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._offset: int | None = None

    async def run_once(self) -> int:
        """One scheduler run: handle the new messages. Returns how many there were."""
        try:
            updates = await self._bot.get_updates(self._offset)
        except NotificationError as exc:
            logger.warning("telegram getUpdates failed: %s", exc)
            return 0
        async with self._session_factory() as db:
            for update in updates:
                # Confirmed by the next getUpdates even if handling it fails, so a bad
                # message can't block the ones after it.
                self._offset = update.update_id + 1
                await handle_update(db, self._bot, update)
        return len(updates)
