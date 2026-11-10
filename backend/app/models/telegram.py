import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TelegramLink(TimestampMixin, Base):
    """A family member's Telegram chat, where their elders' urgent scam alerts go.

    Created when they ask for a connect link: a one-time token (stored hashed) that the bot
    receives as `/start <token>` from the chat to link, before it expires. `chat_id` is set
    once linked; asking for a new link while linked keeps the chat until the new one is used.
    """

    __tablename__ = "telegram_links"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Null until linked. Not unique: two accounts may share one Telegram chat.
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    link_token_hash: Mapped[str | None] = mapped_column(Text, unique=True)
    link_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
