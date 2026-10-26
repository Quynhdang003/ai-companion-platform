import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ElderStatus(StrEnum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class Elder(TimestampMixin, Base):
    __tablename__ = "elders"
    __table_args__ = (
        CheckConstraint(r"phone_e164 ~ '^\+[1-9][0-9]{7,14}$'", name="phone_e164_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    phone_e164: Mapped[str] = mapped_column(Text, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    preferred_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ElderStatus] = mapped_column(
        Enum(ElderStatus, name="status", native_enum=False, create_constraint=True),
        server_default=ElderStatus.PENDING_VERIFICATION.value,
    )
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
