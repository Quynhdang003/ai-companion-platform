import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Null for unknown callers: they still get a session, but no personal data.
    elder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("elders.id", ondelete="CASCADE"), index=True
    )
    session_token_hash: Mapped[str] = mapped_column(Text, unique=True)
    # Set when Dograh's end-of-call webhook links the run to this session.
    workflow_run_id: Mapped[str | None] = mapped_column(Text, unique=True)
    from_number: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
