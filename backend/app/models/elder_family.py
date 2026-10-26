import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FamilyRole(StrEnum):
    OWNER = "owner"
    VIEWER = "viewer"


class ElderFamily(Base):
    __tablename__ = "elder_family"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("elders.id", ondelete="CASCADE"), primary_key=True
    )
    # Separate index: the composite PK only serves lookups by elder_id.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[FamilyRole] = mapped_column(
        Enum(
            FamilyRole,
            name="role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
