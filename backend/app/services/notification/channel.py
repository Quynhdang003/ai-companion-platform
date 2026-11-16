"""Where family notifications go, behind one interface so jobs can be tested with a fake.

Messages carry call metadata and scam type/level only, never anything said in a call.
"""

from typing import Protocol


class NotificationError(Exception):
    """Sending failed for now (network, rate limit, provider error): worth retrying."""


class RecipientUnreachableError(NotificationError):
    """The recipient can't get messages any more (e.g. blocked the bot): stop sending."""


class NotificationChannel(Protocol):
    async def send(self, recipient: str, text: str) -> None:
        """Deliver plain `text` to `recipient` (a Telegram chat id, an email address...)."""
        ...
