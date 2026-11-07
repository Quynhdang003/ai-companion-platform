import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CallLog(TimestampMixin, Base):
    """What happened on a call, from Dograh's end-of-call webhook (one row per call session).

    The call's start time is `call_sessions.started_at`. Conversation content (`transcript`,
    `recording_url`) is kept only for consented (ACTIVE) callers and is read by backend jobs
    and the AI only: web routes never return it.
    """

    __tablename__ = "call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), unique=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    # Dograh's call disposition, as sent (e.g. "completed").
    disposition: Mapped[str | None] = mapped_column(Text)
    # [{"role": "elder" | "assistant", "text": ...}] in call order. None is SQL NULL (not JSON
    # null), so `transcript IS NULL` means "no content kept".
    transcript: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    # Dograh public download link (anyone holding it can download the recording).
    recording_url: Mapped[str | None] = mapped_column(Text)
