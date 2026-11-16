"""Telegram Bot API over plain HTTPS (no SDK): the alert channel and the bot's inbox.

The bot token is part of every Bot API URL, so nothing here may log or raise a URL:
errors carry the method and Telegram's error code only, and httpx's request log (INFO,
with the URL) is kept quiet.
"""

import logging
from functools import lru_cache
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.services.notification.channel import NotificationError, RecipientUnreachableError

# httpx logs every request URL at INFO; Bot API URLs contain the token.
logging.getLogger("httpx").setLevel(logging.WARNING)


class TelegramNotConfiguredError(NotificationError):
    """TELEGRAM_BOT_TOKEN is not set."""


class TelegramChat(BaseModel):
    id: int
    type: str  # "private", "group", "supergroup" or "channel"


class TelegramMessage(BaseModel):
    chat: TelegramChat
    text: str | None = None


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None


class TelegramApi(Protocol):
    """What the jobs use of the bot; `tests/fakes.py` has a fake."""

    async def send(self, recipient: str, text: str) -> None: ...

    async def get_updates(self, offset: int | None) -> list[TelegramUpdate]: ...


class TelegramBot:
    """`NotificationChannel` that sends to Telegram chats, plus `getUpdates` for linking."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    async def send(self, recipient: str, text: str) -> None:
        """Send `text` to the chat with id `recipient`, as plain text."""
        await self._call("sendMessage", {"chat_id": recipient, "text": text})

    async def get_updates(self, offset: int | None) -> list[TelegramUpdate]:
        """New messages to the bot, oldest first.

        Passing the last `update_id` + 1 as `offset` confirms everything before it: Telegram
        then never returns those again, even to a restarted backend.
        """
        params: dict[str, Any] = {"timeout": 0, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        result = await self._call("getUpdates", params)
        try:
            return [TelegramUpdate.model_validate(update) for update in result]
        except (TypeError, ValidationError):
            raise NotificationError("Telegram getUpdates: unexpected result") from None

    async def _call(self, method: str, params: dict[str, Any]) -> Any:
        if not self._token:
            raise TelegramNotConfiguredError("TELEGRAM_BOT_TOKEN is not set")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/bot{self._token}/{method}", json=params
                )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # `from None`: a chained httpx error could print the URL, token included.
            raise NotificationError(f"Telegram {method} failed: {type(exc).__name__}") from None

        if isinstance(body, dict) and body.get("ok") is True:
            return body.get("result")
        code = body.get("error_code") if isinstance(body, dict) else None
        description = str(body.get("description", "")) if isinstance(body, dict) else ""
        # 403: the user blocked the bot or deleted their account; 400 "chat not found".
        if code == 403 or (code == 400 and "chat not found" in description.lower()):
            raise RecipientUnreachableError(f"Telegram {method}: error {code}")
        raise NotificationError(f"Telegram {method}: error {code or response.status_code}")


@lru_cache
def get_telegram_bot() -> TelegramBot:
    settings = get_settings()
    return TelegramBot(settings.telegram_bot_token, settings.telegram_api_base_url)
