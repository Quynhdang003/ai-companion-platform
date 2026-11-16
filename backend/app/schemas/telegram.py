from datetime import datetime

from pydantic import BaseModel


class TelegramStatusOut(BaseModel):
    # Telegram is set up on this server (bot token and username); otherwise nobody can connect.
    enabled: bool
    connected: bool
    linked_at: datetime | None


class TelegramLinkOut(BaseModel):
    # t.me link that opens the bot; works once, until `expires_at`.
    url: str
    expires_at: datetime
